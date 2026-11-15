"""Transactional outbox helpers (audit A01).

A fire persists its NotificationLog AND a ``Delivery`` row per routed
channel in one transaction, BEFORE any external send. A first delivery
attempt is made synchronously for latency; channels that fail with a
retryable error stay ``pending`` and are retried by the DeliveryWorker
with exponential backoff. Semantics are **at-least-once** — a crash after
a send but before the state update leaves the row ``pending``, so the
worker may re-send; destinations that support it dedup on
``idempotency_key``.

These helpers are pure state transitions (no I/O) so they are easy to
test; the dispatcher and worker compose them with the channel manager.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Delivery, DeliveryState, DeliveryStatus, NotificationLog
from ..utils.time import utc_now

if TYPE_CHECKING:
    from ..channels import Notification

MAX_ATTEMPTS = 5
_BASE_BACKOFF_SEC = 30
_CAP_BACKOFF_SEC = 3600
# A delivery denied scheduling (circuit open, rate-limited) never reached its
# transport, so it is DEFERRED — rescheduled without burning a transport
# attempt — and only given up once the whole delivery exceeds this age, so an
# open breaker or sustained rate pressure can't silently drop a notification
# after a handful of denials (audit F22).
MAX_DELIVERY_AGE_SEC = 3600
_DEFER_RETRY_SEC = 30
# A freshly enqueued delivery is scheduled this far out so the worker
# doesn't race the synchronous first attempt the dispatcher makes. If the
# dispatcher crashes before recording that attempt, the row is still due
# within this window and the worker takes over (at-least-once).
OUTBOX_INITIAL_GRACE_SEC = 30
# The synchronous first attempt is bounded by FIRST_ATTEMPT_BUDGET_SEC (the
# dispatcher wraps it in asyncio.wait_for) and the row is leased for the
# longer FIRST_ATTEMPT_LEASE_SEC. Because the lease outlasts both the grace
# window AND the attempt budget, the worker can never claim a row whose first
# attempt is still in flight: by the time the lease expires the attempt has
# been force-settled (sent/failed → lease released) or the process crashed
# (no in-flight send). The budget MUST stay strictly below the lease so an
# overrunning attempt is always abandoned before the worker becomes eligible
# (audit V03). A grace window alone is not ownership.
FIRST_ATTEMPT_BUDGET_SEC = 45
FIRST_ATTEMPT_LEASE_SEC = 60

# Failures that will never improve on retry — fail the delivery at once
# instead of burning MAX_ATTEMPTS backoffs.
_PERMANENT_HINTS = ("channel not found", "channel disabled", "no adapter")


def backoff_seconds(attempts: int) -> int:
    """Exponential backoff for the Nth attempt (1-based), capped."""
    exp = _BASE_BACKOFF_SEC * (2 ** max(0, attempts - 1))
    return min(exp, _CAP_BACKOFF_SEC)


def _is_permanent(error: str | None) -> bool:
    e = (error or "").lower()
    return any(h in e for h in _PERMANENT_HINTS)


def enqueue(
    session: AsyncSession, notification_id: str, channels: list[str],
    overrides_by_name: dict[str, dict | None] | None = None,
    now: datetime | None = None,
    effective_by_name: dict[str, dict | None] | None = None,
    effective_kind_by_name: dict[str, str] | None = None,
    purpose: str = "notification",
    background_only: bool = False,
    allow_actions: bool = True,
) -> list[Delivery]:
    """Create a pending Delivery row per channel (added to the session).

    ``overrides_by_name`` carries the per-route channel overrides captured
    now (audit F03), kept for audit visibility. ``effective_by_name`` carries
    the FULL effective send config (channel base merged with the override)
    frozen now; it is stored on each delivery so every retry targets the SAME
    destination/credentials as the first attempt even if the channel is edited
    meanwhile (audit V01). Escalations are due immediately, without a first-send
    lease: they are sent only by the background worker after commit."""
    overrides_by_name = overrides_by_name or {}
    effective_by_name = effective_by_name or {}
    effective_kind_by_name = effective_kind_by_name or {}
    now = now or utc_now()
    due = now + timedelta(seconds=OUTBOX_INITIAL_GRACE_SEC)
    rows: list[Delivery] = []
    for ch in channels:
        d = Delivery(
            notification_id=notification_id,
            channel=ch,
            purpose=purpose,
            state=DeliveryState.pending,
            attempts=0,
            created_at=now,
            next_attempt_at=now if purpose == "escalation" or background_only else due,
            # Lease the row for the dispatcher's synchronous first attempt,
            # strictly LONGER than the grace window so the worker can't claim
            # it the instant it comes due while the first attempt may still be
            # sending (audit V03/F04). The dispatcher bounds that attempt below
            # this lease and releases it when the attempt settles.
            lease_until=(
                None if purpose == "escalation" or background_only
                else now + timedelta(seconds=FIRST_ATTEMPT_LEASE_SEC)
            ),
            idempotency_key=f"{delivery_notification_id(notification_id, purpose)}:{ch}"[:130],
            channel_overrides=overrides_by_name.get(ch) or None,
            effective_config=effective_by_name.get(ch),
            effective_kind=effective_kind_by_name.get(ch),
        )
        session.add(d)
        if allow_actions and effective_kind_by_name.get(ch) == "telegram":
            from .channel_actions import issue_tokens

            d.action_keyboard = issue_tokens(d, effective_by_name.get(ch) or {}, now)
        rows.append(d)
    return rows


def apply_attempt(
    delivery: Delivery, *, ok: bool, error: str | None = None,
    now: datetime | None = None, permanent: bool = False,
) -> None:
    """Record the outcome of one send attempt on the delivery row.
    ``permanent``: the adapter said a retry cannot succeed — fail now."""
    now = now or utc_now()
    delivery.attempts += 1
    delivery.updated_at = now
    delivery.lease_until = None  # attempt settled → release the claim (F04)
    if ok:
        delivery.state = DeliveryState.sent
        delivery.last_error = None
        delivery.next_attempt_at = None
        return
    delivery.last_error = (error or "unknown")[:500]
    if permanent or _is_permanent(error) or delivery.attempts >= MAX_ATTEMPTS:
        delivery.state = DeliveryState.failed
        delivery.next_attempt_at = None
    else:
        delivery.state = DeliveryState.pending
        delivery.next_attempt_at = now + timedelta(seconds=backoff_seconds(delivery.attempts))


def apply_deferral(
    delivery: Delivery, *, reason: str, now: datetime | None = None, delay_sec: float | None = None,
) -> None:
    """Reschedule a delivery that was denied scheduling (circuit open /
    rate-limited) WITHOUT counting it as a transport attempt (audit F22).

    The delivery stays ``pending`` and is retried after a short delay; it is
    only marked ``failed`` once it exceeds ``MAX_DELIVERY_AGE_SEC`` so a
    persistently-open breaker or saturated rate limiter can't keep it pending
    forever, and expiry is explicit rather than a side effect of attempts.

    ``delay_sec``: the upstream's own Retry-After — wait that long (capped)
    instead of the fixed short delay.
    """
    now = now or utc_now()
    delivery.updated_at = now
    delivery.lease_until = None  # deferral settled the attempt → release (F04)
    delivery.last_error = f"deferred: {reason}"[:500]
    created = delivery.created_at or now
    if (now - created).total_seconds() >= MAX_DELIVERY_AGE_SEC:
        delivery.state = DeliveryState.failed
        delivery.next_attempt_at = None
    else:
        delivery.state = DeliveryState.pending
        wait = _DEFER_RETRY_SEC if delay_sec is None else min(_CAP_BACKOFF_SEC, max(1.0, delay_sec))
        delivery.next_attempt_at = now + timedelta(seconds=wait)


def cancel_delivery(delivery: Delivery) -> None:
    """Stop a queued delivery without spending a transport attempt."""
    delivery.state = DeliveryState.cancelled
    delivery.next_attempt_at = None
    delivery.lease_until = None
    delivery.last_error = None
    delivery.updated_at = utc_now()


def rollup_status(deliveries: list[Delivery]) -> DeliveryStatus:
    """Roll per-channel delivery states up to the notification's status."""
    if not deliveries:
        return DeliveryStatus.failed
    states = [d.state for d in deliveries]
    if any(s == DeliveryState.pending for s in states):
        return DeliveryStatus.pending
    if all(s == DeliveryState.cancelled for s in states):
        return DeliveryStatus.cancelled
    sent = any(s == DeliveryState.sent for s in states)
    failed = any(s == DeliveryState.failed for s in states)
    if sent and failed:
        return DeliveryStatus.partial
    if sent:
        return DeliveryStatus.sent
    return DeliveryStatus.failed


def apply_rollup_to_log(row: NotificationLog, deliveries: list[Delivery]) -> None:
    """Reflect the current delivery states onto the NotificationLog row:
    status + the sent/failed channel sets (pending channels are in
    neither until they settle)."""
    # Escalations have their own outcome and never rewrite the initial fire.
    deliveries = [d for d in deliveries if d.purpose in (None, "notification")]
    row.delivery_status = rollup_status(deliveries)
    row.dispatched_to = [d.channel for d in deliveries if d.state == DeliveryState.sent]
    row.failed_channels = {
        d.channel: (d.last_error or "failed")
        for d in deliveries if d.state == DeliveryState.failed
    }


def notification_from_log(row: NotificationLog, icon: str | None = None) -> Notification:
    """Rebuild a channel Notification from a persisted log row (used by the
    retry worker). ``icon`` comes from the template when available."""
    from ..channels import Notification
    return Notification(
        id=row.id,
        type=row.type,
        severity=row.severity.value,
        icon=icon,
        title=row.title,
        message=row.message or "",
        fired_at=row.fired_at,
        vars_payload=row.vars_payload,
        rule_id=row.rule_id,
        incident_id=row.incident_id,
    )


def delivery_notification_id(notification_id: str, purpose: str) -> str:
    """Distinct, bounded transport identity for an escalation and its retries."""
    if purpose == "escalation":
        return "esc_" + sha256(notification_id.encode()).hexdigest()[:40]
    return notification_id


def escalation_from_log(row: NotificationLog, delivery: Delivery) -> Notification:
    """Reconstruct the same escalation payload on every retry."""
    notif = notification_from_log(row, "⏫")
    age_min = max(0, int((delivery.created_at - row.fired_at).total_seconds() // 60))
    notif.id = delivery_notification_id(row.id, "escalation")
    notif.title = f"ESCALATION (unacked {age_min}min): {row.title}"[:255]
    notif.message = (
        f"{row.message or ''} — critical fired {age_min} min ago, "
        f"still unacknowledged. Ack: POST /v1/log/{row.id}/ack"
    )
    notif.fired_at = delivery.created_at
    return notif
