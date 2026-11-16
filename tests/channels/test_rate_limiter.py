"""Pure-unit tests for app.channels.rate_limiter."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.channels.rate_limiter import RateLimiter


@pytest.fixture
def rl():
    return RateLimiter()


async def test_allows_first_send(rl):
    assert await rl.allow("ch", 10) is True


async def test_unlimited_when_zero(rl):
    """limit=0 means unlimited."""
    for _ in range(100):
        assert await rl.allow("ch", 0) is True


async def test_negative_limit_treated_as_unlimited(rl):
    assert await rl.allow("ch", -5) is True


async def test_under_limit_allows(rl):
    # 5 sends, limit=10 — all allowed
    for _ in range(5):
        assert await rl.allow("ch", 10) is True


async def test_at_limit_blocks(rl):
    for _ in range(3):
        await rl.allow("ch", 3)
    assert await rl.allow("ch", 3) is False


async def test_used_count_grows(rl):
    for _ in range(4):
        await rl.allow("ch", 100)
    assert rl.used("ch") == 4


async def test_used_returns_zero_for_unknown_channel(rl):
    assert rl.used("never_used") == 0


async def test_per_channel_independence(rl):
    for _ in range(3):
        await rl.allow("a", 3)
    # "a" exhausted; "b" still has full budget
    assert await rl.allow("a", 3) is False
    assert await rl.allow("b", 3) is True


async def test_old_entries_expire():
    """Entries older than 60s should age out of the window."""
    rl = RateLimiter()
    for _ in range(3):
        await rl.allow("ch", 3)
    # Force the deque entries to be 61s old
    win = rl._windows["ch"]
    win.clear()
    win.extend([time.monotonic() - 61.0] * 3)
    # Should be allowed again — the cleanup pops them all
    assert await rl.allow("ch", 3) is True
    assert rl.used("ch") == 1


async def test_concurrent_allow_calls_are_serialized():
    """The asyncio.Lock keeps concurrent allow() calls consistent."""
    rl = RateLimiter()
    # 10 concurrent attempts with limit 5 — exactly 5 should succeed
    results = await asyncio.gather(*[rl.allow("ch", 5) for _ in range(10)])
    assert sum(results) == 5


# ── admit(): the exact wait (deterministic clock) ─────────────────────

class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_a_refusal_says_when_the_oldest_send_leaves_the_window():
    clock = _Clock()
    rl = RateLimiter(clock=clock)
    for step in (0, 10, 20):                     # 3 sends at t=0, 10, 20
        clock.now = 1000.0 + step
        assert (await rl.admit("sms", 3)).allowed
    clock.now = 1025.0
    refused = await rl.admit("sms", 3)
    assert refused.allowed is False
    assert refused.retry_after == pytest.approx(35.0)   # the t=0 send leaves at t=60
    clock.now = 1060.0
    assert (await rl.admit("sms", 3)).allowed            # exactly then it fits


async def test_any_60_seconds_hold_at_most_the_limit():
    # The channel guarantee (stricter than the API keys' GCRA burst).
    clock = _Clock()
    rl = RateLimiter(clock=clock)
    sent = []
    for second in range(0, 120):
        clock.now = 1000.0 + second
        while (await rl.admit("gw", 5)).allowed:
            sent.append(second)
    assert all(sum(1 for s in sent if start <= s < start + 60) <= 5 for start in range(0, 120))


async def test_a_lowered_limit_waits_for_enough_sends_to_leave():
    clock = _Clock()
    rl = RateLimiter(clock=clock)
    for step in (0, 10, 20, 30):                 # 4 sends under a limit of 10
        clock.now = 1000.0 + step
        assert (await rl.admit("ch", 10)).allowed
    clock.now = 1035.0                           # the limit drops to 2
    refused = await rl.admit("ch", 2)
    # One more fits once at most one send is in the window: the t=0, 10 and 20
    # sends must leave — the last of them at t=80, 45 s from now.
    assert refused.retry_after == pytest.approx(45.0)


async def test_unlimited_never_refuses_and_keeps_nothing():
    rl = RateLimiter()
    for _ in range(50):
        assert (await rl.admit("ch", 0)).allowed
    assert rl.used("ch") == 0
