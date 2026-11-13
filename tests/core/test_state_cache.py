"""Pure-unit tests for app.core.state_cache."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.core.state_cache import (
    StateCache,
    VarSnapshot,
    get_state_cache,
    reset_state_cache_for_tests,
)


@pytest.fixture
def cache():
    return StateCache()


# ── VarSnapshot ───────────────────────────────────────────────────


def test_snapshot_age_default_uses_monotonic_now():
    snap = VarSnapshot(value=1, ts=time.monotonic() - 5.0, wall_ts=time.time())
    assert 4.5 < snap.age_sec() < 6.0


def test_snapshot_age_with_explicit_now():
    snap = VarSnapshot(value=1, ts=100.0, wall_ts=0.0)
    assert snap.age_sec(now=110.0) == 10.0


# ── Reads on empty cache ──────────────────────────────────────────


def test_get_unknown_returns_none(cache):
    assert cache.get("missing") is None


def test_value_unknown_returns_none(cache):
    assert cache.value("missing") is None


def test_snapshot_empty(cache):
    assert cache.snapshot() == {}


def test_known_names_empty(cache):
    assert cache.known_names() == set()


def test_last_mqtt_ts_starts_none(cache):
    assert cache.last_mqtt_ts() is None


# ── Writes ────────────────────────────────────────────────────────


async def test_set_stores_value(cache):
    ok = await cache.set("battery.soc", 42)
    assert ok is True
    snap = cache.get("battery.soc")
    assert snap is not None and snap.value == 42


async def test_set_updates_last_mqtt_ts_for_mqtt_source(cache):
    await cache.set("x", 1, source_kind="mqtt")
    assert cache.last_mqtt_ts() is not None


async def test_set_does_not_update_last_mqtt_for_other_kinds(cache):
    await cache.set("x", 1, source_kind="http_poll")
    assert cache.last_mqtt_ts() is None


async def test_set_records_source_metadata(cache):
    await cache.set("x", 1, source_topic="foo/bar", source_kind="mqtt")
    snap = cache.get("x")
    assert snap.source_topic == "foo/bar"
    assert snap.source_kind == "mqtt"


async def test_value_returns_raw(cache):
    await cache.set("x", "hello")
    assert cache.value("x") == "hello"


async def test_known_names_after_writes(cache):
    await cache.set("a", 1)
    await cache.set("b", 2)
    assert cache.known_names() == {"a", "b"}


async def test_snapshot_returns_shallow_copy(cache):
    await cache.set("a", 1)
    snap = cache.snapshot()
    # Mutating the snapshot must NOT affect the cache
    snap.clear()
    assert cache.get("a") is not None


async def test_set_overwrites(cache):
    await cache.set("x", 1)
    await cache.set("x", 2)
    assert cache.value("x") == 2


# ── Subscribers ──────────────────────────────────────────────────


async def test_subscriber_called_on_set(cache):
    received = []

    async def listener(name, snap):
        received.append((name, snap.value))

    cache.subscribe(listener)
    await cache.set("a", 100)
    assert received == [("a", 100)]


async def test_subscriber_cancel_stops_callbacks(cache):
    received = []

    async def listener(name, snap):
        received.append(name)

    cancel = cache.subscribe(listener)
    await cache.set("a", 1)
    cancel()
    await cache.set("b", 2)
    assert received == ["a"]


async def test_subscriber_exception_does_not_break_writes(cache):
    """A misbehaving subscriber must not break set()."""

    async def bad(name, snap):
        raise RuntimeError("boom")

    cache.subscribe(bad)
    ok = await cache.set("a", 1)
    assert ok is True
    assert cache.value("a") == 1


async def test_multiple_subscribers_all_fire(cache):
    a = []
    b = []

    async def la(n, s): a.append(n)
    async def lb(n, s): b.append(n)

    cache.subscribe(la)
    cache.subscribe(lb)
    await cache.set("x", 1)
    assert a == ["x"] and b == ["x"]


async def test_no_fanout_when_no_subscribers(cache):
    """Should not raise; just return True."""
    ok = await cache.set("a", 1)
    assert ok is True


# ── Clear ─────────────────────────────────────────────────────────


async def test_clear_all_removes_everything(cache):
    await cache.set("a", 1)
    await cache.set("b", 2)
    n = cache.clear()
    assert n == 2
    assert cache.snapshot() == {}
    assert cache.last_mqtt_ts() is None


async def test_clear_subset_keeps_others(cache):
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)
    n = cache.clear(only={"a", "c"})
    assert n == 2
    assert cache.known_names() == {"b"}


async def test_clear_subset_unknown_keys_no_op(cache):
    await cache.set("a", 1)
    n = cache.clear(only={"never_set"})
    assert n == 0
    assert cache.value("a") == 1


# ── Module singleton ──────────────────────────────────────────────


def test_get_state_cache_singleton():
    a = get_state_cache()
    b = get_state_cache()
    assert a is b


def test_reset_for_tests_replaces_singleton():
    a = get_state_cache()
    reset_state_cache_for_tests()
    b = get_state_cache()
    assert a is not b
