"""Pure-unit tests for app.channels.circuit_breaker."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.channels.circuit_breaker import CircuitBreaker


@pytest.fixture
def breaker():
    return CircuitBreaker(threshold=3, open_sec=60)


async def test_starts_closed(breaker):
    s = breaker.state("ch")
    assert s.state == "closed"
    assert s.consecutive_failures == 0


async def test_allow_closed_channel(breaker):
    assert await breaker.allow("ch") is True


async def test_record_failure_increments_counter(breaker):
    await breaker.record_failure("ch", "boom")
    assert breaker.state("ch").consecutive_failures == 1
    assert breaker.state("ch").state == "closed"  # not yet at threshold
    assert breaker.state("ch").last_error == "boom"


async def test_threshold_failures_open_breaker(breaker):
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    s = breaker.state("ch")
    assert s.state == "open"
    assert s.open_until > time.monotonic()


async def test_open_breaker_blocks_new_sends(breaker):
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    # Same instant — still in open window
    assert await breaker.allow("ch") is False


async def test_open_until_elapsed_transitions_to_half_open(breaker):
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    # Force the open window to be in the past
    breaker.state("ch").open_until = time.monotonic() - 1.0
    assert await breaker.allow("ch") is True
    assert breaker.state("ch").state == "half_open"


async def test_success_closes_half_open(breaker):
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    breaker.state("ch").open_until = time.monotonic() - 1.0
    await breaker.allow("ch")  # half_open
    await breaker.record_success("ch")
    s = breaker.state("ch")
    assert s.state == "closed"
    assert s.consecutive_failures == 0


async def test_record_success_resets_counter(breaker):
    await breaker.record_failure("ch", "boom")
    await breaker.record_failure("ch", "boom")
    await breaker.record_success("ch")
    s = breaker.state("ch")
    assert s.state == "closed"
    assert s.consecutive_failures == 0
    assert s.last_success_at is not None


async def test_failures_truncate_long_error(breaker):
    long = "x" * 1000
    await breaker.record_failure("ch", long)
    assert len(breaker.state("ch").last_error) <= 200


async def test_health_payload_shape(breaker):
    h = breaker.health("ch")
    assert set(h.keys()) >= {
        "state",
        "consecutive_failures",
        "last_error",
        "last_success_at",
        "last_failure_at",
        "reopens_in_sec",
    }
    assert h["state"] == "closed"


async def test_health_open_reports_reopens_in_sec():
    b = CircuitBreaker(threshold=1, open_sec=30)
    await b.record_failure("ch", "boom")
    h = b.health("ch")
    assert h["state"] == "open"
    assert 0 < h["reopens_in_sec"] <= 30


async def test_breakers_are_independent_per_channel(breaker):
    await breaker.record_failure("a", "boom")
    await breaker.record_failure("a", "boom")
    await breaker.record_failure("a", "boom")
    # Channel "a" is open; "b" is unaffected
    assert breaker.state("a").state == "open"
    assert breaker.state("b").state == "closed"
    assert await breaker.allow("b") is True


async def test_low_threshold():
    """threshold=1 → trips on first failure."""
    b = CircuitBreaker(threshold=1, open_sec=10)
    await b.record_failure("ch", "boom")
    assert b.state("ch").state == "open"
    assert await b.allow("ch") is False


# ── F36: per-channel breaker health snapshot for metrics ─────────

async def test_all_health_reports_each_channel_state(breaker):
    """F36: metrics must be able to iterate per-channel breaker health.
    After one channel's breaker opens, all_health reflects it per channel."""
    # ch_a trips open; ch_b stays closed.
    for _ in range(3):
        await breaker.record_failure("ch_a", "boom")
    await breaker.record_success("ch_b")

    snap = breaker.all_health()
    assert snap["ch_a"]["state"] == "open"
    assert snap["ch_b"]["state"] == "closed"
    # It is a real per-channel map, not a single adapter-kinds list.
    assert set(snap) == {"ch_a", "ch_b"}


# ── F37: half-open admits exactly one probe at a time ────────────

async def test_half_open_admits_single_probe(breaker):
    # Trip open, then let the window elapse.
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    assert breaker.state("ch").state == "open"
    breaker.state("ch").open_until = time.monotonic() - 1  # window elapsed

    first = await breaker.allow("ch")   # becomes half_open, reserves the probe
    second = await breaker.allow("ch")  # must be refused while probe in flight
    third = await breaker.allow("ch")
    assert first is True
    assert second is False
    assert third is False
    assert breaker.state("ch").state == "half_open"


async def test_probe_released_on_success_then_closed(breaker):
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    breaker.state("ch").open_until = time.monotonic() - 1
    assert await breaker.allow("ch") is True
    await breaker.record_success("ch")          # probe settles → closed
    assert breaker.state("ch").state == "closed"
    assert await breaker.allow("ch") is True     # normal operation resumes


async def test_probe_released_on_failure_reopens(breaker):
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    breaker.state("ch").open_until = time.monotonic() - 1
    assert await breaker.allow("ch") is True
    await breaker.record_failure("ch", "still down")  # probe fails → reopen
    assert breaker.state("ch").state == "open"
    assert breaker.state("ch").probe_in_flight is False


async def test_release_probe_lets_next_caller_probe(breaker):
    for _ in range(3):
        await breaker.record_failure("ch", "boom")
    breaker.state("ch").open_until = time.monotonic() - 1
    assert await breaker.allow("ch") is True       # reserves
    assert await breaker.allow("ch") is False      # blocked
    await breaker.release_probe("ch")              # caller deferred (e.g. rate)
    assert await breaker.allow("ch") is True       # next caller may probe
