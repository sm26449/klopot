"""Escalation task — re-page unacknowledged criticals.

A critical alert delivered to Telegram at 02:00 that nobody reads is
a missed page. This service turns acknowledgement into an operational
signal: any dispatched (non-suppressed, non-test) critical that is
still unacknowledged ``ALERTD_ESCALATION_AFTER_MIN`` minutes after
firing is queued ONCE through the escalation channel
(``ALERTD_ESCALATION_CHANNEL``; empty, the default, turns escalation
off), and the row is
stamped ``escalated_at``.

Design notes:

- The escalation delivery and ``escalated_at`` are committed together before
  any send. The delivery worker retries it with the ordinary bounded backoff,
  independently of the initial notification's delivery status.
- Acknowledgement cancels queued escalations; an already-running send may finish.
- Rows older than 24h never escalate — protects the first deploy of
  this feature (and long outages) from paging a backlog of ancient
  criticals.
- ``ALERTD_ESCALATION_AFTER_MIN=0`` disables the whole service.
- Ack via ``POST /v1/log/{id}/ack`` before the deadline prevents the
  escalation — that's the point: ack'ing means "a human saw it".
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import false, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import affected_rows, get_session_factory
from ..db.models import Channel, NotificationLog, Severity
from ..metrics import ESCALATIONS_TOTAL
from ..utils.time import utc_now
from . import outbox
from .gating import escalation_unmuted
from .incidents import escalation_allowed

logger = logging.getLogger(__name__)

_RUN_INTERVAL_SEC = 60
_MAX_AGE_H = 24


class EscalationService:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        if get_settings().escalation_after_min <= 0:
            logger.info("escalation disabled (ALERTD_ESCALATION_AFTER_MIN=0)")
            return
        if not get_settings().escalation_channel:
            logger.info("escalation disabled (no ALERTD_ESCALATION_CHANNEL)")
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name="escalation")
        logger.info(
            "escalation task started (after %d min → %s)",
            get_settings().escalation_after_min,
            get_settings().escalation_channel,
        )

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run(self) -> None:
        # Delay the first sweep past boot (migrations/seed contention).
        try:
            await asyncio.wait_for(self._stop_evt.wait(), timeout=60)
            return
        except TimeoutError:
            pass
        while not self._stop_evt.is_set():
            try:
                await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("escalation sweep failed")
            try:
                await asyncio.wait_for(
                    self._stop_evt.wait(), timeout=_RUN_INTERVAL_SEC
                )
            except TimeoutError:
                continue

    async def sweep_once(self) -> int:
        """Durably enqueue due escalations; returns how many were queued."""
        settings = get_settings()
        after_min = settings.escalation_after_min
        if after_min <= 0 or not settings.escalation_channel:
            return 0
        now = utc_now()
        due_before = now - timedelta(minutes=after_min)
        oldest = now - timedelta(hours=_MAX_AGE_H)

        factory = get_session_factory()
        escalated = 0
        async with factory() as session:
            rows = (
                await session.execute(
                    select(NotificationLog)
                    .where(NotificationLog.severity == Severity.critical)
                    .where(NotificationLog.suppressed_reason.is_(None))
                    .where(NotificationLog.acknowledged_at.is_(None))
                    .where(NotificationLog.escalated_at.is_(None))
                    .where(NotificationLog.is_test == false())
                    .where(escalation_allowed())
                    .where(escalation_unmuted(settings.escalation_channel))
                    .where(NotificationLog.fired_at <= due_before)
                    .where(NotificationLog.fired_at >= oldest)
                    .order_by(NotificationLog.fired_at)
                    .limit(20)
                )
            ).scalars().all()

            for row in rows:
                if await self._escalate(row, session):
                    escalated += 1
            if rows:
                await session.commit()
        if escalated:
            ESCALATIONS_TOTAL.labels(
                channel=settings.escalation_channel, outcome="queued",
            ).inc(escalated)
        return escalated

    async def _escalate(
        self, row: NotificationLog, session: AsyncSession,
    ) -> bool:
        settings = get_settings()
        now = utc_now()
        # Claim in the same transaction as enqueue. A concurrent sweep or ack
        # wins at most once; a crash before commit leaves both changes absent.
        claim = await session.execute(
            update(NotificationLog)
            .where(
                NotificationLog.id == row.id,
                NotificationLog.escalated_at.is_(None),
                NotificationLog.acknowledged_at.is_(None),
                escalation_allowed(),
                escalation_unmuted(settings.escalation_channel),
            )
            .values(escalated_at=now)
        )
        if affected_rows(claim) != 1:
            return False
        name = settings.escalation_channel
        channel = (
            await session.execute(select(Channel).where(Channel.name == name))
        ).scalar_one_or_none()
        outbox.enqueue(
            session, row.id, [name], now=now, purpose="escalation",
            effective_by_name={name: dict(channel.config or {})} if channel else None,
            effective_kind_by_name={name: channel.kind.value} if channel else None,
        )
        return True


_service: EscalationService | None = None


def get_escalation_service() -> EscalationService:
    global _service
    if _service is None:
        _service = EscalationService()
    return _service
