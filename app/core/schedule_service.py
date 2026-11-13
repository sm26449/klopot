"""Schedule service — fires alerts on cron schedule.

Different from the rule engine in two ways:

  1. **Direct fire** — no rule evaluation, no state cache. The
     ``schedules`` row says "fire ``daily_summary`` at 21:00 with
     this context"; we just call ``dispatcher.fire()`` when due.
  2. **Slow tick** — checks every 30 s by default (cron has 1-minute
     granularity, so 30 s is plenty). Cheaper than the engine's 1 s
     base tick.

Stored ``next_fire_at`` lets the service survive restarts without
firing-on-resume: on startup we ignore ``next_fire_at`` values from
the past beyond a small grace window (config: 1 minute) — they're
treated as "already fired or skipped".

Cron expressions handled by ``croniter``. Standard 5-field syntax
(minute hour dom month dow). Timezone from settings.tz.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..db.models import Schedule, ScheduleOccurrence
from ..utils.cron import cron_next_utc
from ..utils.time import utc_now
from . import dispatcher as dispatcher_module

logger = logging.getLogger(__name__)


# How far past `next_fire_at` we'll still fire on resume. Older than
# this is treated as "skipped" — the service was down or the cron
# was created in the past. Keeps `daily_summary at 21:00` from
# firing at boot if we were offline at 21:00.
_RESUME_GRACE_SEC = 60.0


class ScheduleService:
    """Single instance per process. Owned by the lifespan."""

    def __init__(self, *, tick_sec: float = 30.0) -> None:
        self._tick_sec = tick_sec
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()
        self._tz: ZoneInfo | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None:
            return
        settings = get_settings()
        try:
            self._tz = ZoneInfo(settings.tz)
        except Exception:
            logger.warning("Bad timezone %r; falling back to UTC", settings.tz)
            self._tz = ZoneInfo("UTC")

        await self._init_next_fire_times()
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name="schedule-service")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def is_alive(self) -> bool:
        """True if the cron tick task started and is still running (F32)."""
        return self._task is not None and not self._task.done()

    # ── Tick loop ─────────────────────────────────────────────────

    async def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("schedule tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_evt.wait(), timeout=self._tick_sec
                )
            except TimeoutError:
                pass

    async def _tick(self) -> None:
        """One pass: fire schedules whose next_fire_at has passed.

        Each due schedule is handled in its OWN session so one failure can't
        poison the batch — replacing the per-fire savepoint, which was
        incompatible with the dispatcher's own commit (audit F26/V06) — and so
        advancing ``next_fire_at`` commits atomically with the notification
        intent (audit V05)."""
        now_utc = utc_now()
        async for session in get_session():
            due_ids = (
                await session.execute(
                    select(Schedule.id)
                    .where(Schedule.enabled.is_(True))
                    .where(Schedule.next_fire_at.is_not(None))
                    .where(Schedule.next_fire_at <= now_utc)
                )
            ).scalars().all()
            break
        for sched_id in due_ids:
            async for session in get_session():
                try:
                    await self._fire_due(session, sched_id, now_utc)
                except Exception:
                    logger.exception("schedule id=%s tick failed", sched_id)
                    await session.rollback()
                break

    async def _fire_due(
        self, session: AsyncSession, sched_id: int, now_utc: datetime
    ) -> None:
        """Advance, claim and fire one due schedule in a single transaction."""
        sched = await session.get(Schedule, sched_id)
        if sched is None or not sched.enabled or sched.next_fire_at is None:
            return  # changed under us since the due scan
        if sched.next_fire_at > now_utc:
            return  # no longer due
        scheduled_at = sched.next_fire_at

        # Resume guard: skip if we're way past the scheduled time.
        gap_sec = (now_utc - scheduled_at).total_seconds()
        if gap_sec > _RESUME_GRACE_SEC:
            logger.warning(
                "Schedule %s overdue by %.0fs — skipping (was the service down?)",
                sched.name, gap_sec,
            )
            await self._advance_next_fire(session, sched, now_utc)
            await session.commit()
            return

        # Stage the advance (NOT committed here). The dispatcher's persist-
        # before-send commit flushes it together with the notification intent,
        # so advancing next_fire_at and persisting the intent are one atomic
        # unit (audit V05): a crash before that commit rolls both back and the
        # occurrence is retried, never advanced-without-intent.
        active = await self._advance_next_fire(session, sched, now_utc)
        if not active:
            await session.commit()  # invalid cron → disabled, don't fire
            return

        # Claim the occurrence so a double-tick or a second instance can't fire
        # it twice — the (schedule_id, scheduled_at) primary key rejects the
        # duplicate (audit V05). It is committed atomically with the advance and
        # the intent by the dispatcher's commit below.
        try:
            await session.execute(
                insert(ScheduleOccurrence).values(
                    schedule_id=sched.id, scheduled_at=scheduled_at,
                )
            )
        except IntegrityError:
            # Already fired by another tick/instance, whose commit also advanced
            # next_fire_at — so this schedule won't be re-selected next tick.
            await session.rollback()
            logger.info(
                "Schedule %s occurrence %s already claimed — skipping",
                sched.name, scheduled_at,
            )
            return

        await self._fire(session, sched, scheduled_at)

    async def _fire(
        self, session: AsyncSession, sched: Schedule, scheduled_at: datetime
    ) -> None:
        """Fire one schedule via the dispatcher.

        The dispatcher persists the notification intent and COMMITS it before
        any external send (persist-before-send). That commit also flushes the
        staged next_fire_at advance and the occurrence row, so the advance, the
        intent and the occurrence guard land together (audit V05). There is no
        savepoint: the dispatcher owns the commit, so we never call a committing
        helper from inside begin_nested (audit V06). On failure we roll back,
        discarding the staged advance so the occurrence is retried."""
        envelope = dispatcher_module.FireEnvelope(
            type=sched.template_type,
            context=dict(sched.context or {}),
            test=False,
            source=f"schedule:{sched.name}",
            rule_id=None,
        )
        try:
            result = await dispatcher_module.fire(envelope, session)
            await session.execute(
                update(Schedule)
                .where(Schedule.id == sched.id)
                .values(last_fired_at=utc_now())
            )
            await session.execute(
                update(ScheduleOccurrence)
                .where(
                    ScheduleOccurrence.schedule_id == sched.id,
                    ScheduleOccurrence.scheduled_at == scheduled_at,
                )
                .values(notification_id=result.id)
            )
            await session.commit()
            logger.info(
                "Schedule %s fired %s — id=%s dispatched=%s",
                sched.name, sched.template_type, result.id, result.dispatched,
            )
        except Exception:
            logger.exception("schedule %s dispatch failed", sched.name)
            await session.rollback()

    async def _advance_next_fire(
        self, session: AsyncSession, sched: Schedule, anchor: datetime
    ) -> bool:
        """Compute the next cron occurrence after ``anchor`` and persist.

        Returns True if the schedule remains active, False if it was disabled
        (invalid cron) and must not fire."""
        try:
            next_at = self._next_cron(sched.cron_expr, anchor)
        except Exception as e:
            logger.warning(
                "Schedule %s: invalid cron %r (%s); disabling",
                sched.name, sched.cron_expr, e,
            )
            await session.execute(
                update(Schedule).where(Schedule.id == sched.id).values(enabled=False)
            )
            return False
        await session.execute(
            update(Schedule)
            .where(Schedule.id == sched.id)
            .values(next_fire_at=next_at)
        )
        return True

    def _next_cron(self, cron_expr: str, anchor: datetime) -> datetime:
        """Return the next firing time AFTER anchor, as naive UTC.

        Cron is interpreted in the service timezone and the civil firing
        time is preserved across DST transitions (B-08). The shared
        :func:`app.utils.cron.cron_next_utc` helper also backs the editor
        preview, so a previewed time and the fired time cannot disagree."""
        return cron_next_utc(cron_expr, anchor, self._tz or ZoneInfo("UTC"))

    # ── Init helpers ──────────────────────────────────────────────

    async def _init_next_fire_times(self) -> None:
        """Compute next_fire_at for any enabled schedule that's
        missing it. Runs on startup."""
        now = utc_now()
        async for session in get_session():
            rows = (
                await session.execute(
                    select(Schedule)
                    .where(Schedule.enabled.is_(True))
                    .where(Schedule.next_fire_at.is_(None))
                )
            ).scalars().all()
            for sched in rows:
                try:
                    nxt = self._next_cron(sched.cron_expr, now)
                except Exception as e:
                    logger.warning(
                        "Schedule %s: invalid cron %r (%s); disabling",
                        sched.name, sched.cron_expr, e,
                    )
                    await session.execute(
                        update(Schedule)
                        .where(Schedule.id == sched.id)
                        .values(enabled=False)
                    )
                    continue
                await session.execute(
                    update(Schedule)
                    .where(Schedule.id == sched.id)
                    .values(next_fire_at=nxt)
                )
            if rows:
                logger.info("Schedule service: initialized %d next_fire_at values", len(rows))
            await session.commit()
            break

    # ── Public reload (called from CRUD endpoints) ───────────────

    async def recompute_next_fire(self, schedule_id: int) -> None:
        """Recompute next_fire_at for one schedule. Call after CRUD
        mutations on cron_expr or enabled."""
        now = utc_now()
        async for session in get_session():
            sched = await session.get(Schedule, schedule_id)
            if sched is None:
                return
            if not sched.enabled:
                await session.execute(
                    update(Schedule)
                    .where(Schedule.id == schedule_id)
                    .values(next_fire_at=None)
                )
                await session.commit()
                return
            await self._advance_next_fire(session, sched, now)
            await session.commit()
            break

    async def recompute_pending(self) -> None:
        """Recompute next_fire_at for every enabled schedule missing it.

        Called after a config import (which nulls next_fire_at on every
        imported schedule, audit A10) so changed crons take effect without
        a restart. Reuses the startup initializer; ensures tz is set even
        when the service loop isn't running (e.g. in tests)."""
        if self._tz is None:
            try:
                self._tz = ZoneInfo(get_settings().tz)
            except Exception:
                self._tz = ZoneInfo("UTC")
        await self._init_next_fire_times()


# ── Module singleton ──────────────────────────────────────────────


_service: ScheduleService | None = None


def get_schedule_service() -> ScheduleService:
    global _service
    if _service is None:
        _service = ScheduleService()
    return _service
