"""Background delivery worker — retries the transactional outbox (A01).

Polls ``deliveries`` rows that are ``pending`` and due, re-sends each
through the channel manager (so breaker + rate-limit still apply), and
records the attempt with exponential backoff. On process restart the
pending rows are simply still in the DB, so the worker resumes them —
reconciliation needs no special code. Delivery is at-least-once.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..db.models import (
    Delivery,
    DeliveryState,
    DeliveryStatus,
    NotificationLog,
    Template,
)
from ..utils.time import utc_now
from . import gating, outbox

logger = logging.getLogger(__name__)


class DeliveryWorker:
    """One per process. Started/stopped by the app lifespan."""

    _BATCH = 50

    def __init__(self, tick_sec: float = 10.0) -> None:
        self._tick_sec = tick_sec
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name="delivery-worker")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def is_alive(self) -> bool:
        """True if the retry worker task started and is still running (F32)."""
        return self._task is not None and not self._task.done()

    async def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                await self.tick()
            except Exception:  # pragma: no cover - never kill the loop
                logger.exception("delivery worker tick failed")
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=self._tick_sec)
            except TimeoutError:
                pass

    async def tick(self) -> int:
        """Process one batch of due deliveries. Returns how many it tried."""
        async for session in get_session():
            n = await self._process_due(session)
            return n
        return 0  # pragma: no cover

    # How long a worker owns a row once it claims it. Covers the retry send
    # so a second worker (or a stuck claim) can't double-send; a crash lets
    # the lease expire and another pass reclaims it (at-least-once).
    _LEASE_SEC = 60

    async def _process_due(self, session: AsyncSession) -> int:
        now = utc_now()
        due = (
            await session.execute(
                select(Delivery)
                .where(
                    Delivery.state == DeliveryState.pending,
                    Delivery.next_attempt_at <= now,
                    # Skip rows currently leased by another attempt — the
                    # dispatcher's in-flight sync attempt, or another worker
                    # (audit F04). A grace window alone is not ownership.
                    or_(Delivery.lease_until.is_(None), Delivery.lease_until < now),
                )
                .order_by(Delivery.next_attempt_at)
                .limit(self._BATCH)
            )
        ).scalars().all()
        if not due:
            return 0

        from ..channels.manager import get_channel_manager
        mgr = get_channel_manager()
        # Cache template icons per type across this batch.
        icons: dict[str, str | None] = {}

        # Capture ids up front: we commit/rollback PER delivery below, which
        # expires the loaded ORM objects, so each row is re-fetched fresh by id.
        due_ids = [d.id for d in due]

        processed = 0
        for delivery_id in due_ids:
            # Commit (and isolate failures) PER delivery so a crash or one bad
            # row can't re-send the earlier settled deliveries of the batch on
            # restart, and a slow send doesn't hold a 50-row transaction open
            # (audit R05).
            try:
                if await self._process_one(session, delivery_id, mgr, icons, now):
                    await session.commit()
                    processed += 1
                else:
                    await session.rollback()  # claim lost to another worker
            except Exception:
                logger.exception("delivery %s failed; rolling back", delivery_id)
                await session.rollback()
                # Record a failed attempt out-of-band so a row that throws every
                # time (a bug, not a transport failure) eventually exhausts its
                # retries and goes terminal, instead of being reclaimed and
                # re-thrown forever with its attempt count frozen (audit C-11).
                try:
                    d = await session.get(Delivery, delivery_id)
                    # Narrow on a local so mypy doesn't assume d.state is still
                    # pending after apply_attempt mutates it below.
                    was_pending = d is not None and d.state == DeliveryState.pending
                    if d is not None and was_pending:
                        outbox.apply_attempt(d, ok=False, error="worker exception during delivery")
                        # If that made the delivery terminal, finish the same
                        # bookkeeping the normal path does: roll the status onto
                        # the log and release the dedup/throttle claim, so the log
                        # doesn't stay 'pending' with the claim held (C-11).
                        if d.state == DeliveryState.failed:
                            await self._finalize_terminal(session, d)
                        await session.commit()
                    else:
                        await session.rollback()
                except Exception:
                    logger.exception("delivery %s: could not record exception attempt", delivery_id)
                    await session.rollback()
        return processed

    async def _finalize_terminal(self, session: AsyncSession, d: Delivery) -> None:
        """Roll a just-failed delivery's status onto its log and release its
        dedup/throttle claim — the terminal-failure bookkeeping the normal path
        does, reused by the worker's exception path (audit C-11)."""
        log = await session.get(NotificationLog, d.notification_id)
        if log is None:
            return
        siblings = (
            await session.execute(
                select(Delivery).where(Delivery.notification_id == d.notification_id)
            )
        ).scalars().all()
        outbox.apply_rollup_to_log(log, list(siblings))
        if log.delivery_status == DeliveryStatus.failed and not log.is_test and log.context_hash:
            from .dedup_claims import release_claim
            await release_claim(session, log.type, log.context_hash, log.id)
            await gating.release_type_reservation(session, log.type, log.id)

    async def _process_one(
        self, session: AsyncSession, delivery_id: int, mgr, icons: dict, now,
    ) -> bool:
        """Claim and attempt one delivery (by id, re-fetched fresh). Returns
        True if it was claimed and processed (caller commits), False if it is
        no longer claimable (another worker got it / it settled)."""
        # Atomically claim the row before any I/O: lease it iff it is still
        # pending and unleased (audit F04).
        claim = await session.execute(
            update(Delivery)
            .where(
                Delivery.id == delivery_id,
                Delivery.state == DeliveryState.pending,
                or_(Delivery.lease_until.is_(None), Delivery.lease_until < now),
            )
            .values(lease_until=now + timedelta(seconds=self._LEASE_SEC))
        )
        if claim.rowcount != 1:
            return False

        d = await session.get(Delivery, delivery_id)
        if d is None:
            return False
        log = await session.get(NotificationLog, d.notification_id)
        if log is None:
            # The notification row is gone (e.g. retention swept it) — nothing
            # to deliver; close the delivery out.
            d.state = DeliveryState.failed
            d.last_error = "notification row gone"
            d.next_attempt_at = None
            d.attempts += 1
            d.lease_until = None  # settled → release the claim (F04)
            return True
        if log.type not in icons:
            tmpl = (
                await session.execute(select(Template).where(Template.type == log.type))
            ).scalar_one_or_none()
            icons[log.type] = tmpl.icon if tmpl else None
        notif = outbox.notification_from_log(log, icons[log.type])
        # Retry with the SAME destination config frozen at enqueue (V01).
        # Rows enqueued before V01 have no effective_config → fall back to
        # the legacy override delta merged over the live base config (F03).
        if d.effective_config is not None:
            effective = {d.channel: d.effective_config}
            overrides = None
        else:
            effective = None
            overrides = {d.channel: d.channel_overrides} if d.channel_overrides else None
        # Dispatch through the adapter KIND frozen at enqueue (audit B-02), so a
        # channel repurposed since then can't reinterpret this delivery. None for
        # legacy rows → dispatch falls back to the live channel kind.
        effective_kind = (
            {d.channel: d.effective_kind} if d.effective_kind is not None else None
        )
        outcome = await mgr.dispatch(
            notif, [d.channel], session,
            overrides_by_name=overrides, effective_by_name=effective,
            effective_kind_by_name=effective_kind,
        )
        if d.channel in outcome.deferred:
            # Breaker open / rate-limited — reschedule without consuming a
            # retry attempt (audit F22).
            outbox.apply_deferral(d, reason=outcome.deferred[d.channel])
        else:
            outbox.apply_attempt(
                d, ok=d.channel in outcome.succeeded,
                error=outcome.failed.get(d.channel),
            )
        # Roll the whole notification's delivery states up onto the log.
        siblings = (
            await session.execute(
                select(Delivery).where(Delivery.notification_id == d.notification_id)
            )
        ).scalars().all()
        outbox.apply_rollup_to_log(log, list(siblings))

        # If this attempt settled the whole notification into a terminal
        # failure, release its admission claim in the SAME transaction that
        # closes the delivery, mirroring the dispatcher's sync-failure path.
        # Otherwise the claim keeps pointing at the dead id and an identical
        # in-window fire ghost-coalesces onto it as 'pending' with no new
        # delivery (audit V04).
        if log.delivery_status == DeliveryStatus.failed and not log.is_test and log.context_hash:
            from .dedup_claims import release_claim
            await release_claim(session, log.type, log.context_hash, log.id)
            # Release the per-type cooldown reservation too (audit B-10), so a
            # fire that failed on every channel does not keep the type throttled
            # for the rest of the window. No-op when it held none (min_repeat=0
            # or a sibling already superseded it).
            await gating.release_type_reservation(session, log.type, log.id)

        # Account the first successful delivery exactly once — the same
        # idempotent CAS the sync dispatch uses (audit F21/V08). When this retry
        # is the first channel to land, it wins the CAS and counts the fire;
        # when a different channel already counted it synchronously, the CAS is a
        # no-op, so a partial sync success followed by this retry is neither
        # dropped nor double-counted.
        if log.dispatched_to and not log.is_test:
            await gating.account_first_success(log, session)
        return True


_worker: DeliveryWorker | None = None


def get_delivery_worker() -> DeliveryWorker:
    global _worker
    if _worker is None:
        _worker = DeliveryWorker()
    return _worker
