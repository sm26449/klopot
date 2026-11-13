"""Escalation task — re-page unacknowledged criticals.

A critical alert delivered to Telegram at 02:00 that nobody reads is
a missed page. This service turns acknowledgement into an operational
signal: any dispatched (non-suppressed, non-test) critical that is
still unacknowledged ``ALERTD_ESCALATION_AFTER_MIN`` minutes after
firing is re-sent ONCE through the escalation channel
(``ALERTD_ESCALATION_CHANNEL``, default ``sms_main``), and the row is
stamped ``escalated_at``.

Design notes:

- One escalation per notification, ever — ``escalated_at`` is set
  even when the escalation dispatch fails, otherwise a broken SMS
  channel would retry every sweep and burst on recovery. A dead
  escalation channel is the channel-health rules' job to catch.
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

from sqlalchemy import select

from ..config import get_settings
from ..db import get_session_factory
from ..db.models import NotificationLog, Severity
from ..metrics import ESCALATIONS_TOTAL
from ..utils.time import utc_now

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
        """Escalate due rows; returns how many were escalated."""
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
                    .where(NotificationLog.is_test.is_(False))
                    .where(NotificationLog.fired_at <= due_before)
                    .where(NotificationLog.fired_at >= oldest)
                    .order_by(NotificationLog.fired_at)
                    .limit(20)
                )
            ).scalars().all()

            for row in rows:
                await self._escalate(row, session, after_min)
                escalated += 1
            if rows:
                await session.commit()
        return escalated

    async def _escalate(
        self, row: NotificationLog, session, after_min: int
    ) -> None:
        from ..channels import Notification
        from ..channels.manager import get_channel_manager

        settings = get_settings()
        age_min = int((utc_now() - row.fired_at).total_seconds() // 60)
        notif = Notification(
            id=f"{row.id}_esc",
            type=row.type,
            severity=row.severity.value,
            icon="⏫",
            title=f"ESCALATION (unacked {age_min}min): {row.title}"[:255],
            message=(
                f"{row.message or ''} — critical fired {age_min} min ago, "
                f"still unacknowledged. Ack: POST /v1/log/{row.id}/ack"
            ),
            fired_at=utc_now(),
            vars_payload=row.vars_payload,
            rule_id=row.rule_id,
        )
        try:
            outcome = await get_channel_manager().dispatch(
                notif, [settings.escalation_channel], session
            )
            ok = bool(outcome.succeeded)
        except Exception:
            logger.exception("escalation dispatch failed for %s", row.id)
            ok = False
        # Stamp regardless of outcome — one escalation per row, ever
        # (see module docstring).
        row.escalated_at = utc_now()
        ESCALATIONS_TOTAL.labels(
            channel=settings.escalation_channel,
            outcome="ok" if ok else "failed",
        ).inc()
        logger.warning(
            "escalated unacked critical %s (%s, %d min) → %s [%s]",
            row.id, row.type, age_min, settings.escalation_channel,
            "ok" if ok else "FAILED",
        )


_service: EscalationService | None = None


def get_escalation_service() -> EscalationService:
    global _service
    if _service is None:
        _service = EscalationService()
    return _service
