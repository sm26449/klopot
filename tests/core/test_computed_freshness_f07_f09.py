"""F07/F08/F09: computed-variable freshness, invalidation and propagation."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.state_cache import StateCache
from app.core.variable_resolver import VariableResolver, VarMapping


def _resolver_with(*mappings):
    cache = StateCache()
    r = VariableResolver(cache)
    r.replace_mappings(list(mappings))
    return r, cache


async def test_computed_ignores_stale_dependency_and_invalidates():
    # F07: once `a` goes stale, `b = a*2` must not keep presenting a value
    # computed from expired evidence — the old output is invalidated.
    r, cache = _resolver_with(
        VarMapping(name="b", source="computed", value_type="number", formula="a*2"),
    )
    await cache.set("a", 5, stale_after_sec=10)
    await r.recompute_computed()
    assert cache.value("b") == 10

    cache.get("a").ts -= 100  # age `a` past its 10s window
    await r.recompute_computed()
    assert cache.value("b") is None  # not left at the stale 10


async def test_computed_chain_reuses_invalidated_old_intermediate():
    # V07: a=3, b=a*2, c=b*2. When `a` goes stale `b` is invalidated — and `c`
    # must be invalidated too, not recomputed from the stale `b` still sitting
    # in the cache snapshot. Before the fix the base context seeded the fixpoint
    # with `b`'s old output, so `c` kept matching rules on a value with no live
    # evidence behind it (invalidation did not propagate transitively).
    r, cache = _resolver_with(
        VarMapping(name="b", source="computed", value_type="number", formula="a*2"),
        VarMapping(name="c", source="computed", value_type="number", formula="b*2"),
    )
    await cache.set("a", 3, stale_after_sec=10)
    await r.recompute_computed()
    assert cache.value("b") == 6
    assert cache.value("c") == 12

    cache.get("a").ts -= 100  # age `a` past its 10s window
    await r.recompute_computed()
    assert cache.value("b") is None   # direct dependent invalidated (F07)
    assert cache.value("c") is None   # transitive dependent invalidated (V07)


async def test_computed_unresolvable_from_start_stays_absent():
    # F07: a computed var that never had a value and can't resolve is left
    # absent (not written as a bogus None tombstone).
    r, cache = _resolver_with(
        VarMapping(name="b", source="computed", value_type="number", formula="a*2"),
    )
    await r.recompute_computed()
    assert cache.get("b") is None


async def test_computed_freshness_refreshes_when_value_unchanged():
    # F08: `a` keeps publishing the same value, so `b` never changes; its
    # freshness clock must still restart or rules would drop a live value.
    r, cache = _resolver_with(
        VarMapping(name="b", source="computed", value_type="number",
                   formula="a*2", stale_after_sec=10),
    )
    await cache.set("a", 5, stale_after_sec=1000)
    await r.recompute_computed()
    assert cache.value("b") == 10

    b = cache.get("b")
    b.ts -= 1000  # b is now far past its 10s staleness window
    assert b.is_stale()

    await r.recompute_computed()  # value unchanged, but `a` is still fresh
    assert cache.value("b") == 10
    assert not cache.get("b").is_stale()  # freshness refreshed (F08)


async def test_schedule_update_propagates_to_computed_dependent():
    # F09: a cron slot change recomputes its computed dependents immediately,
    # not only when some unrelated inbound message happens to arrive.
    r, cache = _resolver_with(
        VarMapping(name="slot", source="schedule", value_type="number",
                   cron="* * * * *", constant_value=5),
        VarMapping(name="derived", source="computed", value_type="number",
                   formula="slot*2"),
    )
    t0 = datetime(2030, 1, 1, 0, 0, 0)
    await r.evaluate_schedules(t0)            # baseline — no fire yet
    assert cache.get("derived") is None

    await r.evaluate_schedules(t0 + timedelta(minutes=2))  # cron fires
    assert cache.value("slot") == 5
    assert cache.value("derived") == 10
