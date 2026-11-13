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

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Delivery, DeliveryState, DeliveryStatus, NotificationLog
from ..utils.time import utc_now

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
) -> list[Delivery]:
    """Create a pending Delivery row per channel (added to the session).

    ``overrides_by_name`` carries the per-route channel overrides captured
    now (audit F03), kept for audit visibility. ``effective_by_name`` carries
    the FULL effective send config (channel base merged with the override)
    frozen now; it is stored on each delivery so every retry targets the SAME
    destination/credentials as the first attempt even if the channel is edited
    meanwhile (audit V01)."""
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
            state=DeliveryState.pending,
            attempts=0,
            next_attempt_at=due,
            # Lease the row for the dispatcher's synchronous first attempt,
            # strictly LONGER than the grace window so the worker can't claim
            # it the instant it comes due while the first attempt may still be
            # sending (audit V03/F04). The dispatcher bounds that attempt below
            # this lease and releases it when the attempt settles.
            lease_until=now + timedelta(seconds=FIRST_ATTEMPT_LEASE_SEC),
            idempotency_key=f"{notification_id}:{ch}"[:130],
            channel_overrides=overrides_by_name.get(ch) or None,
            effective_config=effective_by_name.get(ch),
            effective_kind=effective_kind_by_name.get(ch),
        )
        session.add(d)
        rows.append(d)
    return rows


def apply_attempt(
    delivery: Delivery, *, ok: bool, error: str | None = None,
    now: datetime | None = None,
) -> None:
    """Record the outcome of one send attempt on the delivery row."""
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
    if _is_permanent(error) or delivery.attempts >= MAX_ATTEMPTS:
        delivery.state = DeliveryState.failed
        delivery.next_attempt_at = None
    else:
        delivery.state = DeliveryState.pending
        delivery.next_attempt_at = now + timedelta(seconds=backoff_seconds(delivery.attempts))


def apply_deferral(
    delivery: Delivery, *, reason: str, now: datetime | None = None,
) -> None:
    """Reschedule a delivery that was denied scheduling (circuit open /
    rate-limited) WITHOUT counting it as a transport attempt (audit F22).

    The delivery stays ``pending`` and is retried after a short delay; it is
    only marked ``failed`` once it exceeds ``MAX_DELIVERY_AGE_SEC`` so a
    persistently-open breaker or saturated rate limiter can't keep it pending
    forever, and expiry is explicit rather than a side effect of attempts.
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
        delivery.next_attempt_at = now + timedelta(seconds=_DEFER_RETRY_SEC)


def rollup_status(deliveries: list[Delivery]) -> DeliveryStatus:
    """Roll per-channel delivery states up to the notification's status."""
    if not deliveries:
        return DeliveryStatus.failed
    states = [d.state for d in deliveries]
    if any(s == DeliveryState.pending for s in states):
        return DeliveryStatus.pending
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
    row.delivery_status = rollup_status(deliveries)
    row.dispatched_to = [d.channel for d in deliveries if d.state == DeliveryState.sent]
    row.failed_channels = {
        d.channel: (d.last_error or "failed")
        for d in deliveries if d.state == DeliveryState.failed
    }


def notification_from_log(row: NotificationLog, icon: str | None = None):
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
    )
