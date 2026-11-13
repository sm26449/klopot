"""Lockout decision (pure) + DB-backed check/record."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core import login_guard
from app.db.models import LoginAttempt

NOW = datetime(2026, 11, 7, 12, 0, 0)


def _ts(minutes_ago: float) -> datetime:
    return NOW - timedelta(minutes=minutes_ago)


def test_decide_not_locked_below_threshold():
    d = login_guard.decide(
        now=NOW, window_min=15,
        user_failures=[_ts(1), _ts(2), _ts(3), _ts(4)], ip_failures=[],
        max_user=5, max_ip=20,
    )
    assert d.locked is False


def test_decide_locked_on_user_threshold_with_retry_after():
    # 5 failures; the 5th most recent is 10 min old → lifts in 5 min
    d = login_guard.decide(
        now=NOW, window_min=15,
        user_failures=[_ts(1), _ts(2), _ts(3), _ts(4), _ts(10)], ip_failures=[],
        max_user=5, max_ip=20,
    )
    assert d.locked is True
    assert d.reason == "username"
    assert d.retry_after_sec == 5 * 60


def test_decide_retry_after_uses_nth_most_recent_not_oldest():
    # 6 failures; oldest is 14 min old but the 5th most recent is 8 min old
    fails = [_ts(1), _ts(2), _ts(3), _ts(4), _ts(8), _ts(14)]
    d = login_guard.decide(
        now=NOW, window_min=15, user_failures=fails, ip_failures=[], max_user=5, max_ip=20,
    )
    assert d.retry_after_sec == 7 * 60


def test_decide_locked_on_ip_threshold():
    d = login_guard.decide(
        now=NOW, window_min=15,
        user_failures=[], ip_failures=[_ts(i) for i in range(1, 21)],
        max_user=5, max_ip=20,
    )
    assert d.locked is True
    assert d.reason == "ip"
    assert d.retry_after_sec >= 1


async def test_check_counts_only_failures_after_last_success(db_session):
    base = datetime.utcnow()
    for i in range(5):  # 5 old failures
        db_session.add(LoginAttempt(ts=base - timedelta(minutes=10 - i), username="admin",
                                    ip="192.0.2.1", success=False))
    db_session.add(LoginAttempt(ts=base - timedelta(minutes=4), username="admin",
                                ip="192.0.2.1", success=True))
    db_session.add(LoginAttempt(ts=base - timedelta(minutes=1), username="admin",
                                ip="192.0.2.1", success=False))
    await db_session.commit()

    d = await login_guard.check(
        db_session, username="admin", ip="192.0.2.1", window_min=15, max_user=5, max_ip=20,
    )
    assert d.locked is False  # only 1 failure since the success


async def test_check_ip_lock_spans_usernames(db_session):
    base = datetime.utcnow()
    for i in range(20):
        db_session.add(LoginAttempt(ts=base - timedelta(seconds=i), username=f"u{i}",
                                    ip="192.0.2.9", success=False))
    await db_session.commit()
    d = await login_guard.check(
        db_session, username="someone-new", ip="192.0.2.9", window_min=15, max_user=5, max_ip=20,
    )
    assert d.locked is True
    assert d.reason == "ip"


async def test_record_appends_row(db_session):
    await login_guard.record(db_session, username="admin", ip="1.2.3.4", success=False)
    await db_session.commit()
    from sqlalchemy import select
    rows = (await db_session.execute(select(LoginAttempt))).scalars().all()
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].ip == "1.2.3.4"
