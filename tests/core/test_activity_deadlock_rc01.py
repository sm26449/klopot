"""rc.9 review RC-01: a MySQL deadlock while writing the activity log lost the
batch without a trace in the metrics. Now a transient error is retried and a
final failure is counted."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core import activity as activity_module
from app.core.activity import get_activity_writer, record_event
from app.db.models import SystemEvent
from tests._db import fresh


def _deadlock():
    return OperationalError("INSERT …", {}, Exception(1213, "Deadlock found when trying to get lock"))


@pytest.fixture
def flaky_factory(monkeypatch):
    """The session factory fails ``n`` times with ``error``, then works."""
    from app.db import session as session_module
    real = session_module.get_session_factory
    state = {"left": 0, "error": _deadlock, "calls": 0}

    def factory():
        state["calls"] += 1
        if state["left"] > 0:
            state["left"] -= 1
            raise state["error"]()
        return real()
    monkeypatch.setattr(session_module, "get_session_factory", factory)
    monkeypatch.setattr(activity_module, "_RETRY_BACKOFF_SEC", 0)
    return state


async def test_a_deadlock_is_retried_and_nothing_is_lost(db_engine, db_session, flaky_factory):
    writer = get_activity_writer()
    dropped = writer.dropped
    flaky_factory["left"] = 1
    record_event(source_kind="rule", source_name="r", event="eval_error", detail="x")
    assert await writer.flush() == 1
    assert flaky_factory["calls"] == 2
    assert writer.dropped == dropped
    await fresh(db_session)
    assert (await db_session.execute(select(SystemEvent.event))).scalars().all() == ["eval_error"]


async def test_a_lasting_failure_is_counted(db_engine, db_session, flaky_factory):
    from app.metrics import ACTIVITY_DROPPED_TOTAL
    writer = get_activity_writer()
    dropped, metric = writer.dropped, ACTIVITY_DROPPED_TOTAL._value.get()
    flaky_factory["left"] = 99
    record_event(source_kind="rule", source_name="r", event="eval_error", detail="x")
    record_event(source_kind="rule", source_name="r", event="eval_recovered")
    assert await writer.flush() == 0
    assert flaky_factory["calls"] == activity_module._WRITE_ATTEMPTS
    assert writer.dropped == dropped + 2
    assert ACTIVITY_DROPPED_TOTAL._value.get() == metric + 2


async def test_a_permanent_error_is_not_retried(db_engine, db_session, flaky_factory):
    writer = get_activity_writer()
    flaky_factory.update(left=99, error=lambda: OperationalError("x", {}, Exception(1146, "no such table")))
    record_event(source_kind="rule", source_name="r", event="eval_error")
    assert await writer.flush() == 0
    assert flaky_factory["calls"] == 1


def test_hits_given_back_merge_with_new_ones():
    from datetime import datetime

    from app.core.activity_rules import RuleCache
    cache = RuleCache()
    cache._hits = {1: [2, datetime(2026, 1, 1, 10), "a"]}
    taken = cache.take_hits()
    cache._hits = {1: [1, datetime(2026, 1, 1, 11), "b"]}
    cache.give_back_hits(taken)
    assert cache._hits[1] == [3, datetime(2026, 1, 1, 11), "b"]
