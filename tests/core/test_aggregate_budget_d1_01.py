"""D1-01: a wildcard aggregate must not accumulate members without bound.

Expired members are evicted from storage (not just excluded from the sum),
and a finite member budget caps the no-TTL case. Overflow invalidates the
output (never a falsely-complete sum) and recovers when a slot frees.
"""
from __future__ import annotations

import pytest

from app.core.state_cache import StateCache
from app.core.variable_resolver import VariableResolver, VarMapping

pytestmark = pytest.mark.anyio


class _Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr("app.core.variable_resolver.time.monotonic", c)
    return c


@pytest.fixture
def cache():
    return StateCache()


@pytest.fixture
def resolver(cache):
    return VariableResolver(cache)


def _agg(name="pv.total", topics=("pv/#",), op="sum", stale=None):
    return VarMapping(
        name=name, source="aggregate", value_type="number",
        topics=list(topics), aggregate=op, stale_after_sec=stale,
    )


async def test_expired_members_are_evicted_from_storage(resolver, cache, clock):
    """A stale member is deleted from the buffer on the next recompute, so a
    churning wildcard aggregate plateaus instead of growing forever."""
    resolver.replace_mappings([_agg(stale=100)])
    clock.t = 1000.0
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    clock.t = 1050.0
    await resolver.handle_inbound("pv/2", 20, "mqtt")
    assert set(resolver._agg_buffers["pv.total"]) == {"pv/1", "pv/2"}

    # Jump past pv/1 and pv/2's deadlines; a new member triggers eviction.
    clock.t = 1200.0
    await resolver.handle_inbound("pv/3", 5, "mqtt")
    assert set(resolver._agg_buffers["pv.total"]) == {"pv/3"}   # 1 and 2 gone
    assert cache.value("pv.total") == 5.0


async def test_sweep_evicts_without_an_inbound_message(resolver, cache, clock):
    """When a publisher stops entirely, the clock sweep still evicts its
    expired members (no reload, no message needed)."""
    resolver.replace_mappings([_agg(stale=100)])
    clock.t = 1000.0
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    assert set(resolver._agg_buffers["pv.total"]) == {"pv/1"}

    clock.t = 1200.0
    await resolver.sweep()
    assert resolver._agg_buffers["pv.total"] == {}   # evicted by the sweep
    assert cache.value("pv.total") is None           # empty fresh set tombstone


async def test_member_budget_refuses_and_invalidates(resolver, cache, clock):
    """A no-TTL aggregate can't evict by time, so the member budget bounds it:
    the over-budget member is refused and the output invalidated — never a
    partial sum presented as complete."""
    resolver._max_agg_members = 2
    resolver.replace_mappings([_agg(stale=None)])
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    await resolver.handle_inbound("pv/2", 20, "mqtt")
    assert cache.value("pv.total") == 30.0

    await resolver.handle_inbound("pv/3", 5, "mqtt")      # would be the 3rd member
    assert "pv/3" not in resolver._agg_buffers["pv.total"]   # refused admission
    assert len(resolver._agg_buffers["pv.total"]) == 2
    assert cache.value("pv.total") is None                  # invalidated, not 30 or 35
    assert resolver.overflowed_aggregates() == ["pv.total"]


async def test_updating_existing_member_at_budget_is_allowed(resolver, cache):
    """At the budget, an update to an ALREADY-tracked member still applies —
    only genuinely new members are refused."""
    resolver._max_agg_members = 2
    resolver.replace_mappings([_agg(stale=None)])
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    await resolver.handle_inbound("pv/2", 20, "mqtt")
    await resolver.handle_inbound("pv/1", 99, "mqtt")      # existing member
    assert cache.value("pv.total") == 119.0
    assert resolver.overflowed_aggregates() == []


async def test_overflow_recovers_when_eviction_frees_a_slot(resolver, cache, clock):
    """Overflow is not permanent: once a stale member is evicted the aggregate
    admits the new member and the output recomputes."""
    resolver._max_agg_members = 2
    resolver.replace_mappings([_agg(stale=100)])
    clock.t = 1000.0
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    await resolver.handle_inbound("pv/2", 20, "mqtt")
    await resolver.handle_inbound("pv/3", 5, "mqtt")       # overflow at budget 2
    assert cache.value("pv.total") is None
    assert resolver.overflowed_aggregates() == ["pv.total"]

    # pv/1 and pv/2 expire; retrying pv/3 evicts them and admits pv/3.
    clock.t = 1200.0
    await resolver.handle_inbound("pv/3", 5, "mqtt")
    assert resolver.overflowed_aggregates() == []
    assert set(resolver._agg_buffers["pv.total"]) == {"pv/3"}
    assert cache.value("pv.total") == 5.0


async def test_null_member_clears_overflow_slot(resolver, cache):
    """A JSON-null for a tracked member frees its slot and clears overflow."""
    resolver._max_agg_members = 2
    resolver.replace_mappings([_agg(stale=None)])
    await resolver.handle_inbound("pv/1", 10, "mqtt")
    await resolver.handle_inbound("pv/2", 20, "mqtt")
    await resolver.handle_inbound("pv/3", 5, "mqtt")       # overflow
    assert resolver.overflowed_aggregates() == ["pv.total"]

    await resolver.handle_inbound("pv/2", None, "mqtt")    # frees a slot
    assert resolver.overflowed_aggregates() == []
    await resolver.handle_inbound("pv/3", 5, "mqtt")       # now admitted
    assert set(resolver._agg_buffers["pv.total"]) == {"pv/1", "pv/3"}
    assert cache.value("pv.total") == 15.0
