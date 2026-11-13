"""Daily suppressed-alerts digest.

Throttles, quiet hours, inhibition and snoozes all silence alerts by
design — but silence you can't see becomes mis-tuned config nobody
notices (a too-aggressive cooldown hides a real recurring problem).
Once a day (``ALERTD_DIGEST_HOUR`` local, default 21; -1 disables)
this service fires the built-in ``daily_suppressed_digest`` template
summarizing the last 24h: dispatched count, suppressed count broken
down by reason, and the top suppressed types.

Restart-safe without extra state: before firing, it checks the log
for a digest row in the last 20h — a container restart at 21:0x
can't double-send.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from ..config import get_settings
from ..db import get_session_factory
from ..db.models import NotificationLog
from ..utils.time import utc_now

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SEC = 300
_TEMPLATE_TYPE = "daily_suppressed_digest"


class DigestService:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        if get_settings().digest_hour < 0:
            logger.info("digest disabled (ALERTD_DIGEST_HOUR=-1)")
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name="digest")
        logger.info(
            "digest task started (daily at %02d:00 %s)",
            get_settings().digest_hour, get_settings().tz,
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
        try:
            await asyncio.wait_for(self._stop_evt.wait(), timeout=60)
            return
        except TimeoutError:
            pass
        while not self._stop_evt.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("digest tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_evt.wait(), timeout=_CHECK_INTERVAL_SEC
                )
            except TimeoutError:
                continue

    async def tick(self, *, now_local: datetime | None = None) -> bool:
        """Fire the digest if it's due; returns True when fired."""
        settings = get_settings()
        if settings.digest_hour < 0:
            return False
        local = now_local or datetime.now(ZoneInfo(settings.tz))
        if local.hour != settings.digest_hour:
            return False
        if await self._already_sent_recently():
            return False
        await self._fire_digest()
        return True

    async def _already_sent_recently(self) -> bool:
        factory = get_session_factory()
        cutoff = utc_now() - timedelta(hours=20)
        async with factory() as session:
            row = (
                await session.execute(
                    select(NotificationLog.id)
                    .where(NotificationLog.type == _TEMPLATE_TYPE)
                    .where(NotificationLog.fired_at >= cutoff)
                    .limit(1)
                )
            ).first()
        return row is not None

    async def _fire_digest(self) -> None:
        from . import dispatcher as dispatcher_module

        context = await self.compute_context()
        envelope = dispatcher_module.FireEnvelope(
            type=_TEMPLATE_TYPE,
            context=context,
            test=False,
            source="digest",
        )
        factory = get_session_factory()
        async with factory() as session:
            await dispatcher_module.fire(envelope, session)
            await session.commit()
        logger.info("daily suppressed digest fired: %s", context)

    async def compute_context(self) -> dict:
        """Last-24h stats: dispatched, failed, suppressed by reason, top types."""
        since = utc_now() - timedelta(hours=24)
        factory = get_session_factory()
        async with factory() as session:
            reason_rows = (
                await session.execute(
                    select(NotificationLog.suppressed_reason, func.count())
                    .where(NotificationLog.fired_at >= since)
                    .where(NotificationLog.type != _TEMPLATE_TYPE)
                    .group_by(NotificationLog.suppressed_reason)
                )
            ).all()
            delivery_rows = (
                await session.execute(
                    select(NotificationLog.delivery_status, func.count())
                    .where(NotificationLog.fired_at >= since)
                    .where(NotificationLog.type != _TEMPLATE_TYPE)
                    .group_by(NotificationLog.delivery_status)
                )
            ).all()
            type_rows = (
                await session.execute(
                    select(NotificationLog.type, func.count())
                    .where(NotificationLog.fired_at >= since)
                    .where(NotificationLog.suppressed_reason.is_not(None))
                    .group_by(NotificationLog.type)
                )
            ).all()

        by_delivery = {
            (d.value if hasattr(d, "value") else str(d)): n
            for d, n in delivery_rows if d is not None
        }
        # "dispatched" = reached ≥1 channel (sent + partial), NOT merely
        # "not suppressed" (audit A03): a fully-failed fire is reported
        # as failed, never folded into the dispatched count.
        dispatched = by_delivery.get("sent", 0) + by_delivery.get("partial", 0)
        failed = by_delivery.get("failed", 0)
        by_reason = Counter({r.value: n for r, n in reason_rows if r is not None})
        total_suppressed = sum(by_reason.values())
        top = Counter(dict(type_rows)).most_common(3)
        return {
            "dispatched": dispatched,
            "failed": failed,
            "total_suppressed": total_suppressed,
            "by_reason": ", ".join(
                f"{k}={v}" for k, v in by_reason.most_common()
            ) or "none",
            "top_types": ", ".join(f"{t}×{n}" for t, n in top) or "none",
        }


_service: DigestService | None = None


def get_digest_service() -> DigestService:
    global _service
    if _service is None:
        _service = DigestService()
    return _service
