"""Tests for app.core.variable_resolver — pure logic + cache writes."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.state_cache import StateCache
from app.core.variable_resolver import (
    _MISSING,
    VariableResolver,
    VarMapping,
    _aggregate,
    _coerce,
    _extract_typed,
    _topic_matches,
)

# ── Topic matching ────────────────────────────────────────────────


def test_exact_topic_matches():
    assert _topic_matches("foo/bar", "foo/bar") is True


def test_exact_topic_mismatch():
    assert _topic_matches("foo/bar", "foo/baz") is False


def test_plus_wildcard_matches_one_segment():
    assert _topic_matches("foo/+/baz", "foo/bar/baz") is True
    assert _topic_matches("foo/+", "foo/bar") is True


def test_plus_wildcard_does_not_match_extra_segments():
    assert _topic_matches("foo/+", "foo/bar/baz") is False


def test_hash_wildcard_matches_anything_after():
    assert _topic_matches("foo/#", "foo/bar/baz/qux") is True
    assert _topic_matches("#", "anything/at/all") is True


def test_pattern_longer_than_topic_no_match():
    assert _topic_matches("a/b/c", "a/b") is False


# ── Type coercion ─────────────────────────────────────────────────


def test_coerce_number_int_passes():
    assert _coerce(42, "number") == 42.0


def test_coerce_number_string():
    assert _coerce("3.14", "number") == 3.14


def test_coerce_number_bool_treated_as_int():
    assert _coerce(True, "number") == 1.0
    assert _coerce(False, "number") == 0.0


def test_coerce_number_invalid_returns_none():
    assert _coerce("not_a_number", "number") is None


def test_coerce_number_rejects_non_finite():
    # nan/inf are valid Python floats but invalid JSON — MySQL would reject the
    # vars_payload insert and lose the alert each cycle (audit C-03).
    for v in (float("nan"), float("inf"), float("-inf"), "nan", "inf", "-Infinity"):
        assert _coerce(v, "number") is None


def test_coerce_bool_truthy_strings():
    for v in ("true", "True", "1", "yes", "ON"):
        assert _coerce(v, "bool") is True


def test_coerce_bool_falsy_strings():
    for v in ("false", "0", "no", "off", ""):
        assert _coerce(v, "bool") is False


def test_coerce_bool_from_int():
    assert _coerce(1, "bool") is True
    assert _coerce(0, "bool") is False


def test_coerce_string_stringifies():
    assert _coerce(42, "string") == "42"


def test_coerce_json_passes_through():
    val = {"k": [1, 2]}
    assert _coerce(val, "json") is val


def test_coerce_none_returns_none():
    assert _coerce(None, "number") is None


# ── JSON path extraction ──────────────────────────────────────────


def test_extract_no_path_uses_payload_directly():
    assert _extract_typed("42", None, "number") == 42.0


def test_extract_simple_path():
    assert _extract_typed({"k": 5}, "k", "number") == 5.0


def test_extract_nested_path():
    assert _extract_typed({"a": {"b": {"c": 7}}}, "a.b.c", "number") == 7.0


def test_extract_missing_key_returns_missing_sentinel():
    # Unresolvable path → _MISSING (caller skips the update entirely);
    # None is reserved for a real JSON null (cache invalidation).
    assert _extract_typed({"a": 1}, "b", "number") is _MISSING


def test_extract_path_into_nondict_returns_missing_sentinel():
    assert _extract_typed({"a": "scalar"}, "a.b", "number") is _MISSING


def test_extract_with_path_against_non_dict_returns_missing_sentinel():
    assert _extract_typed("scalar", "a", "number") is _MISSING


# ── Aggregation ───────────────────────────────────────────────────


def test_aggregate_sum():
    assert _aggregate([1, 2, 3], "sum") == 6


def test_aggregate_avg():
    assert _aggregate([2, 4, 6], "avg") == 4.0


def test_aggregate_max():
    assert _aggregate([1, 5, 3], "max") == 5


def test_aggregate_min():
    assert _aggregate([1, 5, 3], "min") == 1


def test_aggregate_empty_returns_none():
    assert _aggregate([], "sum") is None


def test_aggregate_filters_non_numbers():
    assert _aggregate([1, "x", 3, None, 5], "sum") == 9


def test_aggregate_filters_bools():
    """Booleans are subclasses of int but should NOT count as
    numeric data — we want explicit 0/1 from a number variable."""
    assert _aggregate([True, False, 5], "sum") == 5


def test_aggregate_unknown_op_returns_none():
    assert _aggregate([1, 2], "median") is None


# ── Resolver indexing + dispatch ─────────────────────────────────


@pytest.fixture
def cache():
    return StateCache()


@pytest.fixture
def resolver(cache):
    return VariableResolver(cache)


def test_replace_mappings_builds_index(resolver):
    resolver.replace_mappings([
        VarMapping(name="a", source="mqtt", value_type="number", topic="t/a"),
        VarMapping(name="b", source="mqtt", value_type="number", topic="t/+/b"),
    ])
    f = resolver.topic_filter_for_input("mqtt")
    assert "t/a" in f["exact"]
    assert "t/+/b" in f["wildcard"]


def test_known_var_names(resolver):
    resolver.replace_mappings([
        VarMapping(name="x", source="constant", value_type="number", constant_value=1),
    ])
    assert resolver.known_var_names() == {"x"}


def test_topic_filter_returns_empty_for_non_mqtt(resolver):
    f = resolver.topic_filter_for_input("http_poll")
    assert f == {"exact": set(), "wildcard": set()}


async def test_seed_constants_writes_to_cache(resolver, cache):
    resolver.replace_mappings([
        VarMapping(
            name="thresh.soc",
            source="constant",
            value_type="number",
            constant_value=20,
        ),
    ])
    await resolver.seed_constants()
    snap = cache.get("thresh.soc")
    assert snap.value == 20
    assert snap.source_kind == "constant"


async def test_handle_inbound_writes_value(resolver, cache):
    resolver.replace_mappings([
        VarMapping(name="battery.soc", source="mqtt", value_type="number", topic="seplos/soc"),
    ])
    await resolver.handle_inbound("seplos/soc", "42", "mqtt")
    assert cache.value("battery.soc") == 42.0


async def test_handle_inbound_with_json_path(resolver, cache):
    resolver.replace_mappings([
        VarMapping(
            name="pv.power", source="mqtt", value_type="number",
            topic="fronius/data", json_path="W",
        ),
    ])
    await resolver.handle_inbound("fronius/data", {"W": 9000, "V": 240}, "mqtt")
    assert cache.value("pv.power") == 9000.0


async def test_handle_inbound_uncoerceable_writes_none_tombstone(resolver, cache):
    # An uncoerceable payload coerces to None and IS written to the
    # cache as a tombstone, invalidating any stale prior value
    # (audit 2026-05-15: silently dropping bad payloads left dg.cap_w
    # frozen at its last good value during no_data).
    resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t"),
    ])
    await resolver.handle_inbound("t", "not_a_number", "mqtt")
    snap = cache.get("x")
    assert snap is not None
    assert snap.value is None


async def test_handle_inbound_unknown_topic_no_op(resolver, cache):
    resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t/known"),
    ])
    await resolver.handle_inbound("t/other", 1, "mqtt")
    assert cache.get("x") is None


async def test_aggregate_recomputes_on_each_member(resolver, cache):
    resolver.replace_mappings([
        VarMapping(
            name="pv.total",
            source="aggregate",
            value_type="number",
            topics=["pv/1", "pv/2"],
            aggregate="sum",
        ),
    ])
    await resolver.handle_inbound("pv/1", 5000, "mqtt")
    assert cache.value("pv.total") == 5000.0
    await resolver.handle_inbound("pv/2", 3000, "mqtt")
    assert cache.value("pv.total") == 8000.0
    # Update one member — aggregate refreshes
    await resolver.handle_inbound("pv/1", 6000, "mqtt")
    assert cache.value("pv.total") == 9000.0


async def test_aggregate_avg_op(resolver, cache):
    resolver.replace_mappings([
        VarMapping(
            name="grid.avg_v",
            source="aggregate",
            value_type="number",
            topics=["v/1", "v/2", "v/3"],
            aggregate="avg",
        ),
    ])
    await resolver.handle_inbound("v/1", 230, "mqtt")
    await resolver.handle_inbound("v/2", 232, "mqtt")
    await resolver.handle_inbound("v/3", 234, "mqtt")
    assert cache.value("grid.avg_v") == 232.0


async def test_replace_mappings_invalidates_deleted_constant(resolver, cache):
    """A06: deleting/disabling a variable drops it from the enabled set,
    so the next reload must evict its stale cached value — otherwise
    ``/v1/state`` and the engine keep serving a removed constant forever
    (repro: audit extra-results.json → cache_after_variable_delete)."""
    resolver.replace_mappings([
        VarMapping(
            name="audit_deleted_constant", source="constant",
            value_type="number", constant_value=123,
        ),
    ])
    await resolver.seed_constants()
    assert cache.value("audit_deleted_constant") == 123

    # Reload without the variable (delete / disable) → evicted.
    invalidated = resolver.replace_mappings([])
    assert "audit_deleted_constant" in invalidated
    assert cache.get("audit_deleted_constant") is None


async def test_replace_mappings_invalidates_rebound_mqtt(resolver, cache):
    """A06 (rebind): changing a variable's binding (here its topic)
    must evict the value fed by the old source so a reader never mixes
    the old source's value with the new binding."""
    resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t/a"),
    ])
    await resolver.handle_inbound("t/a", "5", "mqtt")
    assert cache.value("x") == 5.0

    invalidated = resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t/b"),
    ])
    assert "x" in invalidated
    assert cache.get("x") is None  # stays empty until t/b delivers


async def test_replace_mappings_preserves_internal_variables(resolver, cache):
    """A06 guard: the invalidation must only touch names this resolver
    manages. Entries written by other producers (the channel breaker's
    ``channel.*`` internals) must survive a variable reload."""
    await cache.set(
        "channel.ui.breaker_state", "closed",
        source_topic=None, source_kind="internal",
    )
    resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t/a"),
    ])
    await resolver.handle_inbound("t/a", "1", "mqtt")

    # Reload a totally different variable set — the internal entry must
    # not be collateral damage.
    resolver.replace_mappings([
        VarMapping(name="y", source="mqtt", value_type="number", topic="t/c"),
    ])
    assert cache.value("channel.ui.breaker_state") == "closed"


async def test_replace_mappings_keeps_unchanged_variable(resolver, cache):
    """A06 no-churn: a variable whose binding is unchanged across a
    reload keeps its cached value (not needlessly evicted)."""
    resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t/a"),
    ])
    await resolver.handle_inbound("t/a", "7", "mqtt")

    invalidated = resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t/a"),
    ])
    assert "x" not in invalidated
    assert cache.value("x") == 7.0


async def test_replace_mappings_resets_aggregates(resolver, cache):
    """Reloading config wipes aggregate buffers — old members no
    longer pollute the new aggregate."""
    resolver.replace_mappings([
        VarMapping(
            name="pv.total", source="aggregate", value_type="number",
            topics=["pv/1"], aggregate="sum",
        ),
    ])
    await resolver.handle_inbound("pv/1", 5000, "mqtt")
    assert cache.value("pv.total") == 5000.0

    # Replace with a new config (different members)
    resolver.replace_mappings([
        VarMapping(
            name="pv.total", source="aggregate", value_type="number",
            topics=["pv/2"], aggregate="sum",
        ),
    ])
    # Old member's value is forgotten — only new member contributes
    await resolver.handle_inbound("pv/2", 3000, "mqtt")
    assert cache.value("pv.total") == 3000.0


# ── A16: aggregate freshness per member ───────────────────────────


def _agg(resolver, stale_after_sec=None):
    resolver.replace_mappings([
        VarMapping(
            name="pv.total", source="aggregate", value_type="number",
            topics=["pv/1", "pv/2"], aggregate="sum",
            stale_after_sec=stale_after_sec,
        ),
    ])


async def test_aggregate_excludes_stale_member(resolver, cache):
    """A member that stopped publishing is dropped from the aggregate once
    it ages past stale_after_sec, instead of inflating it as if fresh."""
    _agg(resolver, stale_after_sec=10)
    with patch("app.core.variable_resolver.time.monotonic") as mono:
        mono.return_value = 1000.0
        await resolver.handle_inbound("pv/1", 5000, "mqtt")
        await resolver.handle_inbound("pv/2", 3000, "mqtt")
        assert cache.value("pv.total") == 8000.0
        # 20 s later pv/2 is stale (>10 s); a fresh pv/1 must recompute
        # without pv/2's stale contribution.
        mono.return_value = 1020.0
        await resolver.handle_inbound("pv/1", 6000, "mqtt")
        assert cache.value("pv.total") == 6000.0


async def test_aggregate_null_invalidates_member(resolver, cache):
    """A JSON null for one member drops that member's contribution
    (audit A16) rather than leaving its last value in the sum."""
    _agg(resolver)
    await resolver.handle_inbound("pv/1", 5000, "mqtt")
    await resolver.handle_inbound("pv/2", 3000, "mqtt")
    assert cache.value("pv.total") == 8000.0
    await resolver.handle_inbound("pv/2", None, "mqtt")
    assert cache.value("pv.total") == 5000.0


async def test_aggregate_all_members_gone_tombstones_to_none(resolver, cache):
    """When every member is stale or invalidated, the aggregate becomes
    None — an explicit tombstone — not the last good value."""
    _agg(resolver, stale_after_sec=10)
    with patch("app.core.variable_resolver.time.monotonic") as mono:
        mono.return_value = 1000.0
        await resolver.handle_inbound("pv/1", 5000, "mqtt")
        await resolver.handle_inbound("pv/2", 3000, "mqtt")
        assert cache.value("pv.total") == 8000.0
        # Jump past the window and invalidate the only member that could
        # still be fresh → no fresh members remain → None.
        mono.return_value = 1020.0
        await resolver.handle_inbound("pv/1", None, "mqtt")
    snap = cache.get("pv.total")
    assert snap is not None and snap.value is None


async def test_aggregate_no_stale_policy_keeps_all_present_members(resolver, cache):
    """Without stale_after_sec there is no time-based staleness: every
    present member contributes (the null fix still applies)."""
    _agg(resolver, stale_after_sec=None)
    with patch("app.core.variable_resolver.time.monotonic") as mono:
        mono.return_value = 1000.0
        await resolver.handle_inbound("pv/1", 5000, "mqtt")
        mono.return_value = 9999.0  # far in the future — still counts
        await resolver.handle_inbound("pv/2", 3000, "mqtt")
        assert cache.value("pv.total") == 8000.0
# ── A32: input_id isolation ───────────────────────────────────────


async def test_input_id_isolation_same_topic(resolver, cache):
    """Two variables bound to different inputs but sharing a topic must
    not cross-update: a message from input 1 only touches input 1's var."""
    resolver.replace_mappings([
        VarMapping(name="a", source="mqtt", value_type="number", topic="t", input_id=1),
        VarMapping(name="b", source="mqtt", value_type="number", topic="t", input_id=2),
    ])
    await resolver.handle_inbound("t", 5, "mqtt", input_id=1)
    assert cache.value("a") == 5.0
    assert cache.get("b") is None

    await resolver.handle_inbound("t", 7, "mqtt", input_id=2)
    assert cache.value("b") == 7.0
    assert cache.value("a") == 5.0  # input 2's message left a untouched


async def test_unbound_variable_updated_by_any_input(resolver, cache):
    """A variable with no input binding (input_id None) accepts any source."""
    resolver.replace_mappings([
        VarMapping(name="u", source="mqtt", value_type="number", topic="t"),
    ])
    await resolver.handle_inbound("t", 3, "mqtt", input_id=99)
    assert cache.value("u") == 3.0
    await resolver.handle_inbound("t", 4, "mqtt", input_id=5)
    assert cache.value("u") == 4.0
# ── A15: computed + schedule variable sources ─────────────────────


async def test_computed_recomputes_from_constants(resolver, cache):
    resolver.replace_mappings([
        VarMapping(name="a", source="constant", value_type="number", constant_value=3),
        VarMapping(name="b", source="constant", value_type="number", constant_value=4),
        VarMapping(name="c", source="computed", value_type="number", formula="a + b"),
    ])
    await resolver.seed_constants()
    await resolver.recompute_computed()
    assert cache.value("c") == 7.0


async def test_computed_reacts_to_mqtt_update(resolver, cache):
    resolver.replace_mappings([
        VarMapping(name="x", source="mqtt", value_type="number", topic="t"),
        VarMapping(name="dbl", source="computed", value_type="number", formula="x * 2"),
    ])
    await resolver.handle_inbound("t", 10, "mqtt")
    assert cache.value("dbl") == 20.0
    await resolver.handle_inbound("t", 21, "mqtt")
    assert cache.value("dbl") == 42.0


async def test_computed_chain_converges(resolver, cache):
    resolver.replace_mappings([
        VarMapping(name="a", source="constant", value_type="number", constant_value=2),
        VarMapping(name="c", source="computed", value_type="number", formula="a + 1"),
        VarMapping(name="d", source="computed", value_type="number", formula="c * 10"),
    ])
    await resolver.seed_constants()
    await resolver.recompute_computed()
    assert cache.value("c") == 3.0
    assert cache.value("d") == 30.0


async def test_computed_missing_dependency_not_set(resolver, cache):
    resolver.replace_mappings([
        VarMapping(name="c", source="computed", value_type="number", formula="missing + 1"),
    ])
    await resolver.recompute_computed()
    assert cache.get("c") is None  # unresolved → left absent, no bogus value


async def test_schedule_sets_value_when_cron_fires_in_window(resolver, cache):
    from datetime import datetime

    resolver.replace_mappings([
        VarMapping(name="tariff", source="schedule", value_type="json",
                   cron="* * * * *", constant_value="offpeak"),
    ])
    # First call establishes a baseline — no fire replayed.
    t0 = datetime(2026, 1, 1, 22, 0, 30)
    await resolver.evaluate_schedules(t0)
    assert cache.get("tariff") is None

    # A minute later the every-minute cron has fired in (t0, t1].
    t1 = datetime(2026, 1, 1, 22, 1, 30)
    await resolver.evaluate_schedules(t1)
    assert cache.value("tariff") == "offpeak"


async def test_schedule_does_not_fire_outside_window(resolver, cache):
    from datetime import datetime

    resolver.replace_mappings([
        VarMapping(name="daily", source="schedule", value_type="json",
                   cron="0 22 * * *", constant_value="on"),
    ])
    await resolver.evaluate_schedules(datetime(2026, 1, 1, 10, 0, 0))  # baseline
    # 10:00 → 10:30, the 22:00 cron did not fire.
    await resolver.evaluate_schedules(datetime(2026, 1, 1, 10, 30, 0))
    assert cache.get("daily") is None
