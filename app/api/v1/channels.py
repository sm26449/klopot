"""``/v1/channels`` — channel CRUD."""
from __future__ import annotations

import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...config import get_settings
from ...db import get_session
from ...db.models import Channel, Template, TemplateChannel
from ...schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate
from ...schemas.common import ChannelKind, Page
from ...schemas.routing import ChannelUsage, ChannelUsageTemplate
from ...secrets_registry import mask_config, merge_secret_update, secret_status
from ...utils.time import utc_now
from ._crud import crud_get_or_404, crud_list, enforce_create_cap, flush_or_409


async def _usage(session: AsyncSession, channel_id: int) -> list[ChannelUsageTemplate]:
    rows = (
        await session.execute(
            select(Template, TemplateChannel)
            .join(TemplateChannel, TemplateChannel.template_id == Template.id)
            .where(TemplateChannel.channel_id == channel_id)
            .order_by(Template.type)
        )
    ).all()
    return [
        ChannelUsageTemplate(
            type=t.type, severity_min=tc.severity_min, enabled=tc.enabled,
        )
        for t, tc in rows
    ]

router = APIRouter()

# Short-TTL cache of channel reachability probes (audit S-17). Keyed by channel
# id + a snapshot of its config, so an edit busts the entry; otherwise a burst of
# /health calls would each open an outbound connection.
_HEALTH_TTL_SEC = 10.0
_health_cache: dict[int, tuple[float, int, dict[str, Any]]] = {}


async def _cached_healthcheck(channel_id: int, config: dict[str, Any], adapter: Any) -> dict[str, Any]:
    cfg_fingerprint = hash(tuple(sorted((str(k), str(v)) for k, v in config.items())))
    now = time.monotonic()
    hit = _health_cache.get(channel_id)
    if hit and hit[1] == cfg_fingerprint and now - hit[0] < _HEALTH_TTL_SEC:
        return hit[2]
    h: dict[str, Any] = await adapter.healthcheck(dict(config))
    _health_cache[channel_id] = (now, cfg_fingerprint, h)
    return h


def _to_read(obj: Channel) -> ChannelRead:
    """Serialize with literal secrets masked (audit 2026-11-07 C-2).

    Every read path goes through here so no handler can leak a
    ``bot_token`` / ``password`` literal to a ``read``-scoped caller.
    """
    out = ChannelRead.model_validate(obj)
    out.config = mask_config("channel", obj.kind, obj.config)
    out.secret_fields_set = secret_status("channel", obj.kind, obj.config)
    return out


@router.get("", response_model=Page[ChannelRead], summary="List channels")
async def list_channels(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    kind: ChannelKind | None = None,
    enabled: bool | None = None,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[ChannelRead]:
    filters = []
    if kind is not None:
        filters.append(Channel.kind == kind)
    if enabled is not None:
        filters.append(Channel.enabled.is_(enabled))
    items, total = await crud_list(
        session, Channel, skip=skip, limit=limit, filters=filters,
        order_by=Channel.name,
    )
    return Page(
        items=[_to_read(i) for i in items],
        total=total, limit=limit, offset=skip,
    )


@router.post(
    "", response_model=ChannelRead, status_code=status.HTTP_201_CREATED,
    summary="Create channel",
)
async def create_channel(
    body: ChannelCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ChannelRead:
    await enforce_create_cap(session, Channel, get_settings().max_channels, entity="Channel")
    obj = Channel(**body.model_dump())
    session.add(obj)
    await flush_or_409(session, "Channel create")
    await session.refresh(obj)
    await record_change(
        session, actor, "channel.create",
        resource_kind="channel", resource_id=str(obj.id),
        after=model_to_dict(obj),
    )
    await session.commit()
    return _to_read(obj)


@router.get("/{channel_id}", response_model=ChannelRead, summary="Get channel")
async def get_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> ChannelRead:
    obj = await crud_get_or_404(session, Channel, channel_id)
    return _to_read(obj)


@router.patch("/{channel_id}", response_model=ChannelRead, summary="Update channel")
async def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ChannelRead:
    obj = await crud_get_or_404(session, Channel, channel_id)
    before = model_to_dict(obj)
    patch = body.model_dump(exclude_unset=True)
    if "config" in patch and patch["config"] is not None:
        # Secret fields omitted / null / masked-echo keep their stored
        # value; "" clears; anything else replaces (secrets_registry).
        kind = patch.get("kind") or obj.kind
        patch["config"] = merge_secret_update("channel", kind, obj.config, patch["config"])
    if getattr(patch.get("kind") or obj.kind, "value", "") == "mqtt":
        from ...channels.mqtt_config import validate_config

        try:
            validate_config(patch.get("config") or obj.config or {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
    if getattr(patch.get("kind") or obj.kind, "value", "") == "sms" and patch.get("config") is not None:
        from ...channels.sms_config import upgrade_legacy
        from ...channels.sms_config import validate_config as validate_sms

        patch["config"] = upgrade_legacy(patch["config"])
        try:
            validate_sms(patch["config"])
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
    if getattr(patch.get("kind") or obj.kind, "value", "") == "telegram":
        from ...channels.telegram_config import validate_actions_config

        try:
            validate_actions_config(patch.get("config") or obj.config or {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
    for k, v in patch.items():
        setattr(obj, k, v)
    await flush_or_409(session, "Channel update")
    await session.refresh(obj)
    await record_change(
        session, actor, "channel.update",
        resource_kind="channel", resource_id=str(obj.id),
        before=before, after=model_to_dict(obj),
    )
    await session.commit()
    return _to_read(obj)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete channel")
async def delete_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    obj = await crud_get_or_404(session, Channel, channel_id)
    used_by = await _usage(session, channel_id)
    if used_by:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CHANNEL_IN_USE",
                "message": f"Channel is routed to by {len(used_by)} template(s); "
                           "remove those routes first.",
                "templates": [t.type for t in used_by],
            },
        )
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "channel.delete",
        resource_kind="channel", resource_id=str(channel_id), before=before,
    )
    await session.commit()


# ── Actions ─────────────────────────────────────────────────────


@router.post(
    "/{channel_id}/test",
    summary="Send a test notification through this channel",
    description=(
        "Bypasses templates / rules / gating — directly invokes the "
        "channel adapter with a synthetic Notification. Useful to "
        "verify credentials and reachability."
    ),
)
async def test_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict:
    from ...channels import REGISTRY, Notification
    from ...channels.base import CHANNEL_TEST_TYPE

    obj = await crud_get_or_404(session, Channel, channel_id)
    cls = REGISTRY.get(obj.kind.value)
    if cls is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No adapter registered for kind={obj.kind.value}",
        )
    adapter = cls()
    # Every test is a new message: its own id, so a gateway that deduplicates
    # on the idempotency key (sms-gateway, webhooks) sends each test instead of
    # replaying the first one while the UI says "sent".
    test_id = f"test_{obj.name}_{secrets.token_hex(4)}"
    notif = Notification(
        id=test_id,
        type=CHANNEL_TEST_TYPE,
        severity="info",
        icon="🧪",
        title=f"Test from Klopot ({obj.name})",
        message="If you can read this, the channel works. Sent from the Klopot admin UI or API to check it.",
        fired_at=utc_now(),
    )
    from ...core.activity import capture_exchanges, record_attempt

    started_at, t0 = utc_now(), time.monotonic()
    with capture_exchanges() as exchange:
        result = await adapter.send(notif, dict(obj.config or {}), idempotency_key=f"{test_id}:{obj.name}")
    # Activity log: the test with its full exchange, like a real attempt.
    record_attempt(
        channel=obj.name, kind="test", started_at=started_at, duration_ms=int((time.monotonic() - t0) * 1000),
        outcome="sent" if result.ok else "deferred" if result.retry_after is not None
        else "permanent" if result.permanent else "failed",
        exchange=exchange, notification_id=test_id, error=result.error, retry_after=result.retry_after,
    )
    # Audited so "this channel was tested and works" is visible (and the setup
    # guide can tick it). The outcome only — never the adapter's response body.
    await record_change(
        session, actor, "channel.test", resource_kind="channel", resource_id=str(obj.id),
        after={"channel": obj.name, "kind": obj.kind.value, "ok": result.ok, "error": (result.error or "")[:200] or None},
    )
    await session.commit()
    return {
        "channel": obj.name,
        "kind": obj.kind.value,
        "ok": result.ok,
        "error": result.error,
        "response": result.response,
    }


@router.get(
    "/{channel_id}/health",
    summary="Channel reachability + breaker state",
)
async def channel_health(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> dict:
    from ...channels import REGISTRY
    from ...channels.manager import get_channel_manager

    obj = await crud_get_or_404(session, Channel, channel_id)
    cls = REGISTRY.get(obj.kind.value)
    breaker_state = get_channel_manager().health(obj.name)
    if cls is None:
        return {
            "name": obj.name,
            "kind": obj.kind.value,
            "reachable": False,
            "error": "no adapter registered",
            **breaker_state,
        }
    adapter = cls()
    # Cache the outbound probe briefly so repeated /health calls can't amplify
    # into a flood of outbound connections (audit S-17); breaker_state above
    # stays live (in-memory, cheap).
    h = await _cached_healthcheck(channel_id, obj.config or {}, adapter)
    if obj.kind.value == "telegram":
        from ...core.telegram_service import get_telegram_service

        h = {**h, "actions": get_telegram_service().health(obj.config or {})}
    return {"name": obj.name, "kind": obj.kind.value, **h, **breaker_state}


@router.get(
    "/{channel_id}/usage",
    response_model=ChannelUsage,
    summary="Templates that route to this channel",
    description=(
        "Lists the templates whose routing includes this channel. A "
        "non-empty list blocks ``DELETE`` (409 CHANNEL_IN_USE) — the UI "
        "shows these so the operator unlinks them first."
    ),
)
async def channel_usage(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> ChannelUsage:
    obj = await crud_get_or_404(session, Channel, channel_id)
    return ChannelUsage(
        channel_id=obj.id,
        channel_name=obj.name,
        templates=await _usage(session, channel_id),
    )


@router.post(
    "/{channel_id}/breaker/reset",
    summary="Force this channel's circuit breaker closed",
    description=(
        "Clears the open window and failure count so the next send is "
        "attempted immediately. Use after fixing the underlying cause "
        "(e.g. rotated a revoked token). Audited as channel.breaker_reset."
    ),
)
async def reset_breaker(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict:
    from ...channels.manager import get_channel_manager

    obj = await crud_get_or_404(session, Channel, channel_id)
    health = await get_channel_manager().reset_breaker(obj.name)
    await record_change(
        session, actor, "channel.breaker_reset",
        resource_kind="channel", resource_id=str(obj.id),
        after={"breaker": health},
    )
    await session.commit()
    return {"name": obj.name, "state": health.get("state", "closed"), "breaker": health}
