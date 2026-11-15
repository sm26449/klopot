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
