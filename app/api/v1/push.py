"""``/v1/push`` — Web Push devices (docs/WEB_PUSH.md).

A browser or installed app asks for the VAPID public key (``/config``),
subscribes with its push service, and registers the result here. Alerts
routed to the ``push`` channel then reach every enabled device whose minimum
severity they meet. Registering needs a signed-in browser session (it is the
device itself); managing devices needs ``admin``.
"""
from __future__ import annotations

import re
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...channels import push as push_channel
from ...db.models import Channel, ChannelKind, PushSubscription, Severity
from ...db.session import get_session
from ...schemas.push import (
    PushConfig,
    PushSubscriptionCreate,
    PushSubscriptionRead,
    PushSubscriptionUpdate,
    PushTestResult,
)
from ...utils.time import utc_now

router = APIRouter()


def device_label(user_agent: str) -> str:
    """"iPhone · Safari", "Windows · Chrome" … from the User-Agent (best effort)."""
    ua = user_agent or ""
    device = next((name for pat, name in (
        (r"iPhone", "iPhone"), (r"iPad", "iPad"), (r"Android", "Android"), (r"Windows", "Windows"),
        (r"Macintosh|Mac OS X", "Mac"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux"),
    ) if re.search(pat, ua)), "Browser")
    browser = next((name for pat, name in (
        (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/|FxiOS", "Firefox"),
        (r"Chrome/|CriOS", "Chrome"), (r"Safari/", "Safari"),
    ) if re.search(pat, ua)), "")
    return f"{device} · {browser}" if browser else device


def _read(row: PushSubscription) -> PushSubscriptionRead:
    return PushSubscriptionRead.model_validate({
        **{c: getattr(row, c) for c in PushSubscriptionRead.model_fields if hasattr(row, c)},
        "service": push_channel.short_endpoint(row.endpoint),
        "min_severity": row.min_severity.value if isinstance(row.min_severity, Severity) else row.min_severity,
    })


async def push_channel_row(session: AsyncSession) -> Channel | None:
    """The instance's push channel: the first enabled one (docs/WEB_PUSH.md)."""
    return (await session.execute(
        select(Channel).where(Channel.kind == ChannelKind.push, Channel.enabled.is_(True)).order_by(Channel.id)
    )).scalars().first()


def _audit_view(row: PushSubscription) -> dict[str, Any]:
    d = model_to_dict(row)
    d.pop("p256dh", None)
    d.pop("auth", None)
    d["endpoint"] = push_channel.short_endpoint(row.endpoint)
    return d


@router.get("/config", response_model=PushConfig, summary="Is Web Push available, and its public key")
async def push_config(
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("read")),
) -> PushConfig:
    ch = await push_channel_row(session)
    if ch is None:
        return PushConfig(enabled=False, reason="no_channel")
    identity, why = push_channel.vapid_identity(dict(ch.config or {}))
    if identity is None:
        return PushConfig(enabled=False, channel=ch.name, reason=why)
    return PushConfig(enabled=True, channel=ch.name, public_key=identity.public_key)


@router.get("/subscriptions", response_model=list[PushSubscriptionRead], summary="Devices that receive Web Push")
async def list_subscriptions(
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("read")),
) -> list[PushSubscriptionRead]:
    rows = (await session.execute(select(PushSubscription).order_by(PushSubscription.id))).scalars().all()
    return [_read(r) for r in rows]


@router.post("/subscriptions", response_model=PushSubscriptionRead, summary="Register this browser / app",
             responses={200: {"description": "Already registered — keys refreshed"}, 201: {"description": "Added"}})
async def register_subscription(
    body: PushSubscriptionCreate,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> PushSubscriptionRead:
    if not actor.is_user:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="A device registers itself from a signed-in browser, not with an API key")
    if not push_channel.endpoint_allowed(body.endpoint):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="endpoint: not a known push service (ALERTD_PUSH_ALLOWED_HOSTS)")
    h = push_channel.endpoint_hash(body.endpoint)
    row = (await session.execute(select(PushSubscription).where(PushSubscription.endpoint_hash == h))).scalars().first()
    if row is None:
        row = PushSubscription(
            endpoint=body.endpoint, endpoint_hash=h, p256dh=body.keys.p256dh, auth=body.keys.auth,
            label=(body.label or "").strip() or device_label(request.headers.get("user-agent", "")),
            min_severity=Severity.warning, enabled=True, created_by=actor.name[:64],
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError:
            # The same device registered twice at once: the other request won.
            await session.rollback()
            row = (await session.execute(
                select(PushSubscription).where(PushSubscription.endpoint_hash == h))).scalars().one()
        else:
            await record_change(session, actor, "push_subscription.create", resource_kind="push_subscription",
                                resource_id=str(row.id), after=_audit_view(row))
            await session.commit()
            await session.refresh(row)
            response.status_code = status.HTTP_201_CREATED
            return _read(row)
    # Known device: refresh its keys (browsers rotate them) and its health.
    # Registering is the user, at the device, asking for notifications: a
    # paused device is enabled again — never left disabled with a clean
    # streak, which hid it from the "only paused devices" check (review K11).
    row.p256dh, row.auth = body.keys.p256dh, body.keys.auth
    row.consecutive_failures, row.last_error = 0, None
    row.enabled, row.paused_reason = True, None
    await session.commit()
    await session.refresh(row)
    return _read(row)


async def _get(session: AsyncSession, sub_id: int) -> PushSubscription:
    row = await session.get(PushSubscription, sub_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Device not found: {sub_id}")
    return row


@router.patch("/subscriptions/{sub_id}", response_model=PushSubscriptionRead, summary="Rename / filter / pause a device")
async def update_subscription(
    sub_id: int,
    body: PushSubscriptionUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> PushSubscriptionRead:
    row = await _get(session, sub_id)
    before = _audit_view(row)
    for k, v in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(row, k, Severity(v) if k == "min_severity" else v.strip() if k == "label" else v)
    if body.enabled:
        row.consecutive_failures, row.paused_reason = 0, None
    elif body.enabled is False:
        row.paused_reason = push_channel.PAUSED_BY_OPERATOR
    await session.flush()
    await record_change(session, actor, "push_subscription.update", resource_kind="push_subscription",
                        resource_id=str(row.id), before=before, after=_audit_view(row))
    await session.commit()
    await session.refresh(row)
    return _read(row)


@router.delete("/subscriptions/{sub_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a device")
async def delete_subscription(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> None:
    row = await _get(session, sub_id)
    before = _audit_view(row)
    await session.delete(row)
    await record_change(session, actor, "push_subscription.delete", resource_kind="push_subscription",
                        resource_id=str(sub_id), before=before)
    await session.commit()


@router.post("/subscriptions/{sub_id}/test", response_model=PushTestResult, summary="Send a test to one device")
async def test_subscription(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> PushTestResult:
    from ...channels.base import CHANNEL_TEST_TYPE, Notification
    from ...core.activity import capture_exchanges, record_attempt

    row = await _get(session, sub_id)
    ch = await push_channel_row(session)
    if ch is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No enabled push channel")
    test_id = f"test_push_{secrets.token_hex(4)}"
    notif = Notification(
        id=test_id, type=CHANNEL_TEST_TYPE, severity="info", icon="🧪",
        title="Test from Klopot",
        message=f"Notifications work on {row.label}. Tap to open Klopot.",
        fired_at=utc_now(),
    )
    started_at, t0 = utc_now(), time.monotonic()
    with capture_exchanges() as exchange:
        result = await push_channel.fan_out(notif, dict(ch.config or {}), only_id=row.id)
    record_attempt(
        channel=ch.name, kind="test", started_at=started_at, duration_ms=int((time.monotonic() - t0) * 1000),
        outcome="sent" if result.ok else "deferred" if result.retry_after is not None
        else "permanent" if result.permanent else "failed",
        exchange=exchange, notification_id=test_id, error=result.error, retry_after=result.retry_after,
    )
    await record_change(session, actor, "push_subscription.test", resource_kind="push_subscription",
                        resource_id=str(sub_id), after={"label": row.label, "ok": result.ok,
                                                        "error": (result.error or "")[:200] or None})
    await session.commit()
    delivered = int((result.response or {}).get("delivered", 0))
    return PushTestResult(ok=result.ok and delivered > 0, error=result.error or (
        None if delivered else "the device did not receive it (removed or unreachable)"), delivered=delivered)
