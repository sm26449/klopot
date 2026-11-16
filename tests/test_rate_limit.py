"""The per-minute limiter (GCRA) behind an API key's rate limit — pure, with
a clock the test moves."""
from __future__ import annotations

import pytest

from app.utils.rate_limit import PerMinuteLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_a_quiet_key_may_send_its_whole_minute_at_once_then_waits(clock):
    rl = PerMinuteLimiter(clock=clock)
    assert all(rl.admit("k", 3).allowed for _ in range(3))
    refused = rl.admit("k", 3)
    assert not refused.allowed
    assert refused.retry_after == pytest.approx(20.0)        # one slot refills every 60/3 s
    clock.now += 19.9
    assert not rl.admit("k", 3).allowed
    clock.now += 0.1
    assert rl.admit("k", 3).allowed


def test_a_refusal_spends_nothing(clock):
    rl = PerMinuteLimiter(clock=clock)
    for _ in range(2):
        rl.admit("k", 2)
    for _ in range(50):
        assert not rl.admit("k", 2).allowed
    clock.now += 30
    assert rl.admit("k", 2).allowed, "refused requests did not push the next one back"


def test_the_steady_rate_is_the_limit(clock):
    rl = PerMinuteLimiter(clock=clock)
    admitted = 0
    for _ in range(600):                                     # ten minutes, a request every second
        admitted += rl.admit("k", 30).allowed
        clock.now += 1
    # Requests at t = 0..599: the 30-request allowance, spent by t = 59 while it
    # refills one every 2 s, then one every 2 s — 330 for a full 600 s, 329
    # because the window ends a second short.
    assert admitted == 329


def test_uneven_intervals_still_add_up_to_the_minute(clock):
    rl = PerMinuteLimiter(clock=clock)
    assert sum(rl.admit("k", 7).allowed for _ in range(8)) == 7    # 60/7 is not exact in floats


def test_keys_are_independent(clock):
    rl = PerMinuteLimiter(clock=clock)
    assert rl.admit(1, 1).allowed
    assert not rl.admit(1, 1).allowed
    assert rl.admit(2, 1).allowed


def test_a_changed_limit_keeps_the_allowance_already_spent(clock):
    """The spent allowance is kept as time: 10 requests at 60/min are 10 s of
    the minute, which at 6/min (10 s each) leaves room for 5 — a lower limit
    takes effect at once, and an edit does not refill the key."""
    rl = PerMinuteLimiter(clock=clock)
    for _ in range(10):
        rl.admit("k", 60)
    assert [rl.admit("k", 6).allowed for _ in range(6)] == [True] * 5 + [False]


def test_only_keys_back_at_full_allowance_are_pruned(clock):
    rl = PerMinuteLimiter(clock=clock, max_idle=2)
    rl.admit("busy", 1)                                      # limited for the next minute
    rl.admit("a", 60)
    clock.now += 5                                           # "a" is full again, "busy" is not
    rl.admit("b", 60)                                        # over max_idle: prune
    assert "a" not in rl._tat and "busy" in rl._tat
    assert not rl.admit("busy", 1).allowed


def test_forget_and_validation(clock):
    rl = PerMinuteLimiter(clock=clock)
    rl.admit("k", 1)
    rl.forget("k")
    assert rl.admit("k", 1).allowed
    with pytest.raises(ValueError):
        rl.admit("k", 0)
