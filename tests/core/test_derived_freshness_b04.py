"""B-04: a derived value must not stay "fresh" after the evidence it was
built from has expired.

Two confirmed gaps:

* **Scenario A (aggregate).** Members arrive at t=100 and t=109 with TTL 10.
  At t=111 the cached total still counted the expired t=100 member, and the
  total read *fresh* because its own recompute was only 2 s old.
* **Scenario B (computed).** A direct variable has TTL 10 and a computed
  dependent has TTL 300. With no new messages the direct value expires at
  t=110, yet the computed result produced at t=100 kept reading fresh until
  t=400.

The fix pins a derived value's expiry to its evidence — the earliest
contributing member for an aggregate, the soonest dependency for a computed —
and runs a clock-driven sweep so expiry acts even with no inbound message.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.state_cache import StateCache, VarSnapshot
from app.core.variable_resolver import VariableResolver, VarMapping

pytestmark = pytest.mark.anyio


class _Clock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# ── VarSnapshot: the dual freshness bound ─────────────────────────


def test_snapshot_stale_via_evidence_deadline_before_age_window():
    """A derived snapshot expires at its evidence deadline even when its own
    age window hasn't elapsed — the core false-fresh bug."""
    snap = VarSnapshot(
        value=30, ts=109.0, wall_ts=0.0,
        stale_after_sec=300, expires_at=110.0,   # TTL far out, evidence near
    )
    assert not snap.is_stale(now=109.5)   # before the evidence deadline
    assert snap.is_stale(now=111.0)       # evidence lapsed though age is 2 s


def test_snapshot_age_window_still_applies_without_evidence_deadline():
    """The classic age-based ceiling is unchanged when no explicit evidence
    deadline is set (H-4 behavior preserved)."""
    snap = VarSnapshot(value=5, ts=100.0, wall_ts=0.0, stale_after_sec=10)
    assert not snap.is_stale(now=105.0)
    assert snap.is_stale(now=111.0)


# ── Scenario A: aggregate evidence expiry ─────────────────────────


async def test_aggregate_expires_with_its_earliest_member():
    """The aggregate total goes stale when its soonest member expires, not
    when its own (later) recompute ages out."""
    clock = _Clock()
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings([
        VarMapping(name="pv.total", source="aggregate", value_type="number",
                   topics=["pv/1", "pv/2"], aggregate="sum", stale_after_sec=10),
    ])
    with patch("app.core.state_cache.time.monotonic", clock):
        clock.t = 100.0
        await r.handle_inbound("pv/1", 10, "mqtt")
        clock.t = 109.0
        await r.handle_inbound("pv/2", 20, "mqtt")

    snap = cache.get("pv.total")
    assert snap.value == 30.0
    # Deadline is the EARLIEST member (t=100 + 10), not the recompute at 109.
    assert snap.expires_at == 110.0
    assert not snap.is_stale(now=109.5)
    assert snap.is_stale(now=111.0)         # Scenario A: no longer false-fresh


async def test_sweep_recomputes_aggregate_dropping_expired_member():
    """The clock sweep recomputes the aggregate from its still-fresh members
    with no inbound message — the total becomes 20 (only the live member) and
    its deadline advances to that member's expiry."""
    clock = _Clock()
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings([
        VarMapping(name="pv.total", source="aggregate", value_type="number",
                   topics=["pv/1", "pv/2"], aggregate="sum", stale_after_sec=10),
    ])
    with patch("app.core.state_cache.time.monotonic", clock):
        clock.t = 100.0
        await r.handle_inbound("pv/1", 10, "mqtt")
        clock.t = 109.0
        await r.handle_inbound("pv/2", 20, "mqtt")
        assert cache.value("pv.total") == 30.0

        clock.t = 111.0                      # pv/1 (t=100) now past its 10 s TTL
        await r.sweep()

    snap = cache.get("pv.total")
    assert snap.value == 20.0                # only the fresh pv/2 remains
    assert snap.expires_at == 119.0          # 109 + 10
    assert not snap.is_stale(now=111.0)


async def test_sweep_is_idempotent_no_fanout_when_unchanged():
    """A sweep that changes nothing must not re-emit the aggregate to
    subscribers (no spurious WebSocket churn)."""
    clock = _Clock()
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings([
        VarMapping(name="pv.total", source="aggregate", value_type="number",
                   topics=["pv/1"], aggregate="sum", stale_after_sec=1000),
    ])
    with patch("app.core.state_cache.time.monotonic", clock):
        clock.t = 100.0
        await r.handle_inbound("pv/1", 10, "mqtt")

        seen: list[str] = []

        async def _sub(name, snap):
            seen.append(name)

        cache.subscribe(_sub)
        clock.t = 101.0
        await r.sweep()                      # nothing expired, value unchanged
    assert seen == []                        # no fanout


# ── Scenario B: computed evidence expiry ──────────────────────────


async def test_computed_expiry_bounded_by_short_ttl_dependency():
    """A long-TTL computed inherits its short-TTL dependency's deadline, so it
    stops reading fresh when the dependency expires."""
    clock = _Clock()
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings([
        VarMapping(name="derived", source="computed", value_type="number",
                   formula="base + 1", stale_after_sec=300),
    ])
    with patch("app.core.state_cache.time.monotonic", clock):
        clock.t = 100.0
        await cache.set("base", 5, stale_after_sec=10)   # base expires at 110
        await r.recompute_computed()

    snap = cache.get("derived")
    assert snap.value == 6
    # Bounded by base's deadline (110), NOT derived's own 100+300.
    assert snap.expires_at == 110.0
    assert not snap.is_stale(now=109.0)
    assert snap.is_stale(now=111.0)          # Scenario B: no longer false-fresh


async def test_sweep_invalidates_computed_when_dependency_expired():
    """With no new messages, the sweep invalidates a computed whose only
    dependency's TTL has lapsed, instead of leaving a value with no live
    evidence behind it."""
    clock = _Clock()
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings([
        VarMapping(name="derived", source="computed", value_type="number",
                   formula="base + 1", stale_after_sec=300),
    ])
    with patch("app.core.state_cache.time.monotonic", clock):
        clock.t = 100.0
        await cache.set("base", 5, stale_after_sec=10)
        await r.recompute_computed()
        assert cache.value("derived") == 6

        clock.t = 111.0                      # base now stale, no new message
        await r.sweep()
    assert cache.value("derived") is None    # evidence gone → invalidated


async def test_computed_over_constant_keeps_own_ttl_only():
    """A computed whose dependencies never expire (constant) is bounded only
    by its own TTL, not forced to expire early."""
    clock = _Clock()
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings([
        VarMapping(name="k", source="constant", value_type="number",
                   constant_value=7),
        VarMapping(name="derived", source="computed", value_type="number",
                   formula="k * 2", stale_after_sec=50),
    ])
    with patch("app.core.state_cache.time.monotonic", clock):
        clock.t = 100.0
        await r.seed_constants()
        await r.recompute_computed()

    snap = cache.get("derived")
    assert snap.value == 14
    assert snap.expires_at == 150.0          # 100 + own 50; constant doesn't bound


async def test_computed_chain_inherits_soonest_deadline_transitively():
    """b = a*2 (a TTL 10), c = b*2 (own TTL 999): c inherits a's deadline
    through b."""
    clock = _Clock()
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings([
        VarMapping(name="b", source="computed", value_type="number", formula="a*2"),
        VarMapping(name="c", source="computed", value_type="number",
                   formula="b*2", stale_after_sec=999),
    ])
    with patch("app.core.state_cache.time.monotonic", clock):
        clock.t = 100.0
        await cache.set("a", 3, stale_after_sec=10)      # a expires at 110
        await r.recompute_computed()

    assert cache.value("b") == 6
    assert cache.value("c") == 12
    assert cache.get("b").expires_at == 110.0            # bounded by a
    assert cache.get("c").expires_at == 110.0            # inherited through b
