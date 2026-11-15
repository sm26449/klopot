"""Push channel — Web Push (VAPID) to browsers and installed apps.

Design: docs/WEB_PUSH.md. Devices register from the admin UI
(``POST /v1/push/subscriptions``) into the ``push_subscriptions`` table; this
adapter fans an alert out to every enabled device whose ``min_severity`` the
alert reaches.

Config (one ``push`` channel per instance — devices subscribe to its key)::

    {
      "vapid_private_ref": "KLOPOT_SECRET_VAPID_PRIVATE",
      "vapid_subject": "mailto:ops@example.com",
      "ttl_sec": 86400
    }

The public key is derived from the private one (``GET /v1/push/config``
hands it to the browser). Only the crypto comes from ``pywebpush`` /
``py_vapid``: the POST goes through ``safe_request`` (egress screening, IP
pinning, Activity-log exchange) and only to allowlisted push services. The
payload is encrypted end to end (aes128gcm) with the device's keys — the push
service never sees the alert text.
"""
from __future__ import annotations

import asyncio
import base64
import fnmatch
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, false, select, update

from ..config import get_settings
from ..db.models import PushSubscription, Severity
from ..utils.http_retry import retry_after_or_default
from ..utils.redact import redact_url, transport_error_text
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from ..utils.time import utc_now
from ._secrets import resolve_secret
from .base import CHANNEL_TEST_TYPE, BaseChannel, Notification, SendResult

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
URGENCY = {"info": "low", "warning": "normal", "critical": "high"}
DEFAULT_TTL_SEC = 86400
MAX_PAYLOAD_BYTES = 3000          # 4096 on the wire minus encryption overhead, with margin
DISABLE_AFTER_FAILURES = 20
# push_subscriptions.paused_reason values (migration 0037).
PAUSED_BY_SERVICE = "service"
PAUSED_BY_OPERATOR = "operator"


# ── Pure helpers ────────────────────────────────────────────────────


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def endpoint_allowed(endpoint: str, patterns: list[str] | None = None) -> bool:
    """https only, and the host must be a known push service (docs/WEB_PUSH.md)."""
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    for pat in patterns if patterns is not None else get_settings().push_allowed_host_list:
        if fnmatch.fnmatchcase(host, pat) and (pat.startswith("*.") or host == pat):
            return True
    return False


def short_endpoint(endpoint: str) -> str:
    """Shown in the UI / API: the push service and the token's tail."""
    parts = urlsplit(endpoint)
    tail = parts.path.rstrip("/").rsplit("/", 1)[-1]
    return f"{parts.hostname}/…{tail[-8:]}" if tail else str(parts.hostname)


def reaches(min_severity: str, severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(min_severity, 1)


def notification_url(notif: Notification) -> str:
    """Where tapping the notification goes — relative, resolved by the service worker."""
    if notif.type == CHANNEL_TEST_TYPE:
        return "/admin/#/account"
    return f"/admin/#/log?id={notif.id}"


def topic_for(notif_type: str) -> str:
    """Web Push ``Topic`` (≤ 32 URL-safe chars): a queued, undelivered repeat
    of the same alert type is replaced on the push service."""
    return base64.urlsafe_b64encode(hashlib.sha256(notif_type.encode()).digest()).decode()[:32]


def build_payload(notif: Notification) -> bytes:
    """The JSON the service worker shows, trimmed to fit a push message."""
    title = f"{notif.icon} {notif.title}" if notif.icon else notif.title
    data: dict[str, Any] = {
        "title": title[:200],
        "body": notif.message or "",
        "severity": notif.severity,
        "tag": notif.type,
        "url": notification_url(notif),
        "ts": int(notif.fired_at.timestamp() * 1000) if notif.fired_at else None,
    }
    raw = json.dumps(data, ensure_ascii=False).encode()
    if len(raw) > MAX_PAYLOAD_BYTES:
        over = len(raw) - MAX_PAYLOAD_BYTES
        body = data["body"].encode()
        data["body"] = body[: max(0, len(body) - over - 3)].decode(errors="ignore") + "…"
        raw = json.dumps(data, ensure_ascii=False).encode()
    return raw


# ── VAPID ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VapidIdentity:
    private_key: str
    public_key: str      # base64url, uncompressed P-256 point — the browser's applicationServerKey
    subject: str


def vapid_public_key(private_key: str) -> str:
    """Derive the applicationServerKey from the private key."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid import Vapid02

    v = Vapid02.from_string(private_key=private_key)
    point = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(point).decode().rstrip("=")


def vapid_identity(config: dict[str, Any]) -> tuple[VapidIdentity | None, str | None]:
    """(identity, None) or (None, why it cannot send)."""
    private_key = resolve_secret(config, "vapid_private", "vapid_private_ref")
    subject = str(config.get("vapid_subject") or config.get("subject") or "").strip()
    if not private_key:
        return None, "push: the VAPID private key is not set (vapid_private_ref)"
    if not subject.startswith(("mailto:", "https:")):
        return None, "push: vapid_subject must be a mailto: or https: contact"
    try:
        public_key = vapid_public_key(private_key)
    except Exception as e:  # malformed key
        return None, f"push: the VAPID private key is not valid ({type(e).__name__})"
    return VapidIdentity(private_key, public_key, subject), None


def vapid_headers(identity: VapidIdentity, endpoint: str) -> dict[str, str]:
    from py_vapid import Vapid02

    parts = urlsplit(endpoint)
    claims = {"sub": identity.subject, "aud": f"{parts.scheme}://{parts.netloc}",
              "exp": int(time.time()) + 12 * 3600}
    signed = Vapid02.from_string(private_key=identity.private_key).sign(claims)
    return {k: v for k, v in signed.items() if k.lower() == "authorization"}


# ── One device ─────────────────────────────────────────────────────


@dataclass
class DeviceOutcome:
    id: int
    delivered: bool
    status: int | None = None
    gone: bool = False
    retry_after: float | None = None
    error: str | None = None
    # The push service was never reached (timeout, connection or DNS failure):
    # that says something about our network, nothing about the device.
    transport: bool = False


async def send_to_device(
    sub: PushSubscription, payload: bytes, identity: VapidIdentity, *,
    ttl: int, urgency: str, topic: str | None, timeout_sec: float = 10.0,
) -> DeviceOutcome:
    if not endpoint_allowed(sub.endpoint):
        return DeviceOutcome(sub.id, False, error="endpoint is not an allowed push service")
    from pywebpush import WebPusher

    info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
    try:
        body = WebPusher(info).encode(payload, content_encoding="aes128gcm")["body"]
    except Exception as e:  # malformed device keys
        return DeviceOutcome(sub.id, False, gone=True, error=f"device keys unusable: {type(e).__name__}")
    headers = {"TTL": str(ttl), "Urgency": urgency, "Content-Encoding": "aes128gcm",
               "Content-Type": "application/octet-stream", **vapid_headers(identity, sub.endpoint)}
    if topic:
        headers["Topic"] = topic
    try:
        r = await safe_request("POST", sub.endpoint, content=body, headers=headers, timeout=timeout_sec,
                               block_private=get_settings().block_private_egress, max_response_bytes=16384)
    except ResponseTooLarge as e:
        return DeviceOutcome(sub.id, False, error=e.reason)
    except EgressBlocked as e:   # includes a name that does not resolve
        return DeviceOutcome(sub.id, False, error=e.reason, transport=True)
    except httpx.TimeoutException:
        return DeviceOutcome(sub.id, False, error="push service timeout", transport=True)
    except httpx.HTTPError as e:
        return DeviceOutcome(sub.id, False, error=transport_error_text(e)[:200], transport=True)
    if r.status_code in (200, 201, 202):
        return DeviceOutcome(sub.id, True, status=r.status_code)
    detail = redact_url(f"HTTP {r.status_code}: {r.text[:160]}")
    if r.status_code in (404, 410):
        return DeviceOutcome(sub.id, False, status=r.status_code, gone=True, error=detail)
    if r.status_code in (429, 503):
        return DeviceOutcome(sub.id, False, status=r.status_code, error=detail,
                             retry_after=retry_after_or_default(r.headers.get("retry-after")))
    return DeviceOutcome(sub.id, False, status=r.status_code, error=detail)


async def record_outcomes(outcomes: list[DeviceOutcome], labels: dict[int, str]) -> None:
    """Persist per-device state: success, failure streak, removal of dead devices."""
    from ..core.activity import record_event
    from ..db import get_session

    now = utc_now().replace(microsecond=0)
    async for s in get_session():
        for o in outcomes:
            if o.delivered:
                await s.execute(update(PushSubscription).where(PushSubscription.id == o.id).values(
                    last_success_at=now, consecutive_failures=0, last_error=None))
            elif o.gone:
                await s.execute(delete(PushSubscription).where(PushSubscription.id == o.id))
                record_event(source_kind="push_device", source_id=o.id, source_name=labels.get(o.id, str(o.id)),
                             event="device_removed", detail=o.error)
            elif o.retry_after is None:
                row = await s.get(PushSubscription, o.id)
                if row is None:
                    continue
                row.last_failure_at, row.last_error = now, (o.error or "")[:500]
                if o.transport:
                    # Shown on the device, never counted: an outage on our side
                    # would otherwise pause every device after 20 attempts, and
                    # nothing would re-enable them when the network came back.
                    continue
                if not row.enabled:
                    # Paused meanwhile (by the operator, while this send was in
                    # flight): its streak no longer matters (Copilot C19).
                    continue
                row.consecutive_failures = (row.consecutive_failures or 0) + 1
                if row.consecutive_failures >= DISABLE_AFTER_FAILURES:
                    row.enabled, row.paused_reason = False, PAUSED_BY_SERVICE
                    record_event(source_kind="push_device", source_id=o.id, source_name=row.label,
                                 event="device_disabled", detail=o.error)
        await s.commit()
        break


# ── Channel ────────────────────────────────────────────────────────


async def _devices(severity: str | None, only_id: int | None = None) -> list[PushSubscription]:
    from ..db import get_session

    async for s in get_session():
        q = select(PushSubscription).where(PushSubscription.enabled.is_(True))
        if only_id is not None:
            q = select(PushSubscription).where(PushSubscription.id == only_id)
        rows = list((await s.execute(q)).scalars().all())
        if only_id is None and severity is not None:
            rows = [r for r in rows if reaches(_sev(r.min_severity), severity)]
        return rows
    return []


async def _auto_paused(severity: str | None) -> int:
    """Devices the service paused itself (20 refusals in a row) that this
    alert would have reached — as recorded in ``paused_reason`` (review K11),
    so a device the operator keeps paused is never counted."""
    from ..db import get_session

    async for s in get_session():
        rows = (await s.execute(select(PushSubscription).where(
            PushSubscription.enabled == false(),
            PushSubscription.paused_reason == PAUSED_BY_SERVICE))).scalars().all()
        return sum(1 for r in rows if severity is None or reaches(_sev(r.min_severity), severity))
    return 0


def _sev(v: Severity | str) -> str:
    return v.value if isinstance(v, Severity) else str(v)


async def fan_out(notif: Notification, config: dict[str, Any], *, only_id: int | None = None) -> SendResult:
    identity, why = vapid_identity(config)
    if identity is None:
        return SendResult(ok=False, error=why, permanent=True)
    # A channel test reaches every enabled device, whatever its minimum severity.
    severity = None if notif.type == CHANNEL_TEST_TYPE else notif.severity
    devices = await _devices(severity, only_id)
    if not devices:
        paused = 0 if only_id is not None else await _auto_paused(severity)
        if paused:
            # "Sent to nobody" must not look like a delivery.
            return SendResult(
                ok=False, permanent=True, response={"devices": 0, "delivered": 0, "paused": paused},
                error=f"{paused} push device(s) paused after repeated failures; re-enable them under Devices")
        return SendResult(ok=True, response={"devices": 0, "delivered": 0})
    payload = build_payload(notif)
    ttl = int(config.get("ttl_sec") or DEFAULT_TTL_SEC)
    urgency = URGENCY.get(notif.severity, "normal")
    topic = None if notif.type == CHANNEL_TEST_TYPE else topic_for(notif.type)
    outcomes = list(await asyncio.gather(*(
        send_to_device(d, payload, identity, ttl=ttl, urgency=urgency, topic=topic) for d in devices)))
    # Every device refusing our identity (401/403) says our VAPID key or
    # subject is wrong, not that the devices are: never count that against
    # them (review K11). One device refusing while others accept is its own.
    refused_us = all(o.status in (401, 403) for o in outcomes)
    if refused_us:
        for o in outcomes:
            o.transport = True
    await record_outcomes(outcomes, {d.id: d.label for d in devices})
    delivered = sum(o.delivered for o in outcomes)
    response = {"devices": len(devices), "delivered": delivered,
                "results": [{"id": o.id, "delivered": o.delivered, "status": o.status, "removed": o.gone,
                             **({"error": o.error} if o.error else {})} for o in outcomes]}
    if delivered:
        return SendResult(ok=True, response=response)
    errors = "; ".join(o.error or "?" for o in outcomes)[:300]
    if refused_us:
        errors = f"every push service refused our VAPID identity (key or subject): {errors}"[:300]
    waits = [o.retry_after for o in outcomes if o.retry_after is not None]
    if waits and len(waits) == len(outcomes):
        return SendResult(ok=False, error=errors, response=response, retry_after=max(waits))
    if all(o.gone for o in outcomes):
        # Every device is gone (and now removed): nothing left to retry.
        return SendResult(ok=True, response=response)
    return SendResult(ok=False, error=errors, response=response)


class PushChannel(BaseChannel):
    kind = "push"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        return await fan_out(notif, config)

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        identity, why = vapid_identity(config)
        return {"reachable": identity is not None, **({"error": why} if why else {})}
