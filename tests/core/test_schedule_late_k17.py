"""An occurrence that comes due while the service runs is fired, however late (review K17).

The "overdue by more than 60 s — was the service down?" guard ran on every
tick. A tick lasts as long as its synchronous first sends (up to ~45 s each)
and the next one starts 30 s after it ends, so an occurrence due early in a
slow tick, or retried after a transient database error, was found more than
60 s late and skipped with only a warning. The guard now only skips what was
due before the service started.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.core.schedule_service import ScheduleService
from app.db.models import Schedule

pytestmark = pytest.mark.anyio


async def test_late_occurrence_while_running_is_fired(db_engine, db_session):
    svc = ScheduleService()
    svc._tz = ZoneInfo("UTC")
    svc._started_at = datetime.utcnow() - timedelta(minutes=10)   # running for 10 minutes
    db_session.add(Schedule(id=71, name="late", cron_expr="*/5 * * * *", template_type="x", context={},
                            enabled=True, next_fire_at=datetime.utcnow() - timedelta(seconds=95)))
    await db_session.commit()
    fake_fire = AsyncMock(return_value=type("R", (), {"id": "x", "dispatched": True})())
    with patch("app.core.schedule_service.dispatcher_module.fire", fake_fire):
        await svc._tick()
    fake_fire.assert_called_once()


async def test_occurrence_missed_while_down_is_still_skipped(db_engine, db_session):
    svc = ScheduleService()       # just started
    svc._tz = ZoneInfo("UTC")
    db_session.add(Schedule(id=72, name="missed", cron_expr="*/5 * * * *", template_type="x", context={},
                            enabled=True, next_fire_at=datetime.utcnow() - timedelta(minutes=20)))
    await db_session.commit()
    fake_fire = AsyncMock()
    with patch("app.core.schedule_service.dispatcher_module.fire", fake_fire):
        await svc._tick()
    fake_fire.assert_not_called()
