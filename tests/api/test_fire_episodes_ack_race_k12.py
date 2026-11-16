"""Re-announcing an unannounced episode: acknowledged ones stay quiet, and two
repeats at once announce it once (review K12).

The pre-release audit fix lets a repeat go through the gates again while no firing notice of the
episode has gone out. Two gaps: it ignored an acknowledgement given while the
first firing was snoozed (the notice went out after someone took the
incident), and ``_announced`` was a plain read — on MySQL the second of two
concurrent repeats read a snapshot taken before the first committed its
notice, so both announced (two SMS, two Pushover emergencies).
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import delete, func, select

from app.core import fire_service, incidents
from app.db.models import Incident, NotificationLog, Snooze
from tests._db import fresh
from tests.api.test_fire_episodes_unannounced import (
    CTX,
    _delivered,
    _firing,
    _setup,
    _snooze_everything,
)


async def test_an_acknowledged_episode_is_not_announced_later(db_engine, db_session):
    await _setup(db_session)
    await _snooze_everything(db_session)
    first = await _firing(db_session, "f1", **CTX)
    assert first.result.suppressed_reason == "snoozed"
    incident = await db_session.get(Incident, first.incident_id)
    await incidents.acknowledge(db_session, incident, "operator")
    await db_session.commit()

    await db_session.execute(delete(Snooze))
    await db_session.commit()
    after = await _firing(db_session, "f1", **CTX)
    assert after.episode == "repeat"
    assert await _delivered(db_session, first.incident_id) == 0, "someone already took it"


@pytest.mark.mysql
async def test_two_repeats_at_once_announce_the_episode_once(db_engine, db_session):
    from app.db import session as session_module

    await _setup(db_session)
    await _snooze_everything(db_session)
    first = await _firing(db_session, "f1", **CTX)
    await db_session.execute(delete(Snooze))
    await db_session.commit()

    factory = session_module._session_factory

    async def repeat(summary):
        # Each repeat reads first (its snapshot), then waits for the episode
        # row; the dispatcher commits its notice before the send, which is
        # when the other repeat gets the row.
        async with factory() as session:
            out = await fire_service.fire_episode(
                session, source_kind="alertmanager", source_key="am:1:f1", name="DiskFull",
                type="am_critical", context={**CTX, "summary": summary}, source="alertmanager:prom")
            await session.commit()
            return out

    for attempt in range(5):
        await asyncio.gather(repeat(f"9{attempt}% a"), repeat(f"9{attempt}% b"))

    assert await _delivered(db_session, first.incident_id) == 1
    await fresh(db_session)
    firing = (await db_session.execute(select(func.count()).select_from(NotificationLog).where(
        NotificationLog.incident_id == first.incident_id))).scalar_one()
    assert firing == 2, f"announced {firing - 1} times"   # the snoozed first firing + one announcement
