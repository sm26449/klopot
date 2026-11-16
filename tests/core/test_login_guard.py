"""Lockout decision (pure) + DB-backed check/record."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core import login_guard
from app.db.models import LoginAttempt

NOW = datetime(2026, 11, 7, 12, 0, 0)
LIMITS = login_guard.Limits(window_min=15, per_user_and_ip=5, per_user=50, per_ip=20)
HERE, ELSEWHERE = "192.0.2.1", "198.51.100.7"


def _ts(minutes_ago: float) -> datetime:
    return NOW - timedelta(minutes=minutes_ago)


def _from(ip: str, *minutes_ago: float) -> list[tuple[datetime, str | None]]:
    return [(_ts(m), ip) for m in minutes_ago]


def _decide(user_failures, ip_failures=(), ip=HERE, limits=LIMITS):
    return login_guard.decide(now=NOW, limits=limits, user_failures=list(user_failures),
                              ip_failures=list(ip_failures), ip=ip)


def test_decide_not_locked_below_threshold():
    assert _decide(_from(HERE, 1, 2, 3, 4)).locked is False


def test_decide_locked_on_user_threshold_with_retry_after():
    # 5 failures from this address; the 5th most recent is 10 min old → lifts in 5 min
    d = _decide(_from(HERE, 1, 2, 3, 4, 10))
    assert d.locked is True
    assert d.reason == "username"
    assert d.retry_after_sec == 5 * 60


def test_decide_retry_after_uses_nth_most_recent_not_oldest():
    # 6 failures; oldest is 14 min old but the 5th most recent is 8 min old
    assert _decide(_from(HERE, 1, 2, 3, 4, 8, 14)).retry_after_sec == 7 * 60


def test_failures_from_another_address_do_not_lock_this_one():
    """Review F8: five tries from anywhere used to lock the admin out of the
    LAN too. Now they lock the username only where they came from."""
    failures = _from(ELSEWHERE, 1, 2, 3, 4, 5, 6)
    assert _decide(failures, ip=HERE).locked is False
    assert _decide(failures, ip=ELSEWHERE).reason == "username"


def test_the_per_user_ceiling_locks_everywhere():
    """A distributed guesser still meets a limit: per_user from any address."""
    limits = login_guard.Limits(window_min=15, per_user_and_ip=5, per_user=8, per_ip=20)
    spread = [(_ts(i), f"203.0.113.{i}") for i in range(1, 9)]          # 8 addresses, one each
    d = _decide(spread, ip=HERE, limits=limits)
    assert d.locked is True
    assert d.reason == "username_everywhere"


def test_decide_locked_on_ip_threshold():
    d = _decide([], ip_failures=[_ts(i) for i in range(1, 21)])
    assert d.locked is True
    assert d.reason == "ip"
    assert d.retry_after_sec >= 1


async def test_check_counts_only_failures_after_last_success(db_session):
    base = datetime.utcnow()
    for i in range(5):  # 5 old failures
        db_session.add(LoginAttempt(ts=base - timedelta(minutes=10 - i), username="admin",
                                    ip=HERE, success=False))
    db_session.add(LoginAttempt(ts=base - timedelta(minutes=4), username="admin", ip=HERE, success=True))
    db_session.add(LoginAttempt(ts=base - timedelta(minutes=1), username="admin", ip=HERE, success=False))
    await db_session.commit()

    d = await login_guard.check(db_session, username="admin", ip=HERE, limits=LIMITS)
    assert d.locked is False  # only 1 failure since the success


async def test_check_ip_lock_spans_usernames(db_session):
    base = datetime.utcnow()
    for i in range(20):
        db_session.add(LoginAttempt(ts=base - timedelta(seconds=i), username=f"u{i}",
                                    ip="192.0.2.9", success=False))
    await db_session.commit()
    d = await login_guard.check(db_session, username="someone-new", ip="192.0.2.9", limits=LIMITS)
    assert d.locked is True
    assert d.reason == "ip"


async def test_ipv6_addresses_count_by_their_64(db_session):
    """A client gets a whole /64: one budget per /128 was one per request."""
    for i in range(5):
        await login_guard.record(db_session, username="admin", ip=f"2001:db8:1:2::{i + 1:x}", success=False)
    await db_session.commit()
    d = await login_guard.check(db_session, username="admin", ip="2001:db8:1:2:ffff::9", limits=LIMITS)
    assert d.locked is True
    assert d.reason == "username"
    other = await login_guard.check(db_session, username="admin", ip="2001:db8:1:3::1", limits=LIMITS)
    assert other.locked is False


async def test_record_appends_row(db_session):
    await login_guard.record(db_session, username="admin", ip="1.2.3.4", success=False)
    await login_guard.record(db_session, username="admin", ip="2001:db8::1", success=False)
    await db_session.commit()
    from sqlalchemy import select
    rows = (await db_session.execute(select(LoginAttempt).order_by(LoginAttempt.id))).scalars().all()
    assert [r.success for r in rows] == [False, False]
    assert [r.ip for r in rows] == ["1.2.3.4", "2001:db8::/64"]
