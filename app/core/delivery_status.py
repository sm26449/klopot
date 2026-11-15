"""Delivery-status derivation and dedup disposition (audit A02 + A03).

Pure, I/O-free logic shared by the dispatcher (write path), the log
API / digest (read path), and the regression tests. Keeping it here —
not inline in the dispatcher — lets every consumer agree on the single
definition of "was this actually delivered?" instead of each inferring
it from ``suppressed_reason IS NULL`` (the A03 bug: a fully-failed row
has no suppression reason yet reached nobody).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..db.models import DeliveryStatus, NotificationLog, SuppressedReason


def compute_delivery_status(
    suppressed_reason: SuppressedReason | str | None,
    dispatched_to: Sequence[str] | None,
    failed_channels: Mapping[str, Any] | None,
) -> DeliveryStatus:
    """Derive the settled outcome of a fire from its persisted fields.

    - any ``suppressed_reason`` → ``suppressed`` (never reached dispatch)
    - ≥1 success and ≥1 failure → ``partial``
    - ≥1 success, no failure   → ``sent``
    - no success               → ``failed`` (all channels failed, or a
      pre-gating-fix row that dispatched to nothing)
    """
    if suppressed_reason is not None:
        return DeliveryStatus.suppressed
    succeeded = bool(dispatched_to)
    failed = bool(failed_channels)
    if succeeded and failed:
        return DeliveryStatus.partial
    if succeeded:
        return DeliveryStatus.sent
    return DeliveryStatus.failed


def status_of(row: NotificationLog) -> DeliveryStatus:
    """The row's ``delivery_status``, recomputed if a pre-0009 row left
    it NULL — so the read path never has to special-case the gap."""
    if row.delivery_status is not None:
        return row.delivery_status
    return compute_delivery_status(
        row.suppressed_reason, row.dispatched_to, row.failed_channels
    )


def should_coalesce(existing: NotificationLog, this_suppressed_reason: str | None) -> bool:
    """Whether a new fire should dedup (coalesce) onto ``existing``.

    Dedup exists for idempotency — collapse a burst of identical fires
    into one row. But coalescing blindly on (type, context) resurrects
    stale dispositions (audit A02): a re-enabled template keeps
    returning its old ``disabled`` row, and a real alert inherits a
    prior ``test`` row. So coalesce only when the NEW fire's disposition
    matches what ``existing`` settled as:

    - new fire will **dispatch** (``this_suppressed_reason is None``):
      coalesce only onto a prior *success* (``sent``/``partial``) — the
      genuine idempotency case. A prior ``failed`` or ``suppressed`` row
      must NOT mask a fire that can now be delivered.
    - new fire is **suppressed**: coalesce only onto a prior suppression
      with the *same* reason — this preserves "one row per storm" for a
      sustained throttle/inhibit/snooze without masking a change.

    ``is_test`` is matched separately by the caller's query, so a test
    and a real fire never meet here.
    """
    existing_status = status_of(existing)
    if this_suppressed_reason is None:
        # sent/partial = genuine idempotency; pending = delivery still
        # in flight via the outbox worker (A01), so a duplicate fire
        # collapses onto it rather than queuing a second delivery. A
        # prior ``failed`` (retries exhausted) or ``suppressed`` must NOT
        # mask a fire that can now be delivered.
        return existing_status in (
            DeliveryStatus.sent, DeliveryStatus.partial, DeliveryStatus.pending,
        )
    return (
        existing_status is DeliveryStatus.suppressed
        and existing.suppressed_reason is not None
        and existing.suppressed_reason.value == this_suppressed_reason
    )
