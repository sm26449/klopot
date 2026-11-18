"""Tests for app.core.engine.

The engine drives a tick loop. We don't need to run the loop to
test the logic — we drive ``_eval_rule`` and ``_tick`` directly
with a fake state cache and assert the resulting state changes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.engine import RuleEngine, _RuleRuntime, get_engine
from app.core.state_cache import StateCache
from app.db.models import Rule
from tests._db import fresh


@pytest.fixture
async def engine_with_cache():
    """RuleEngine with a fresh StateCache (not the module singleton)."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    return engine, cache


@pytest.fixture
async def seeded_rule(db_session, make_rule, make_template):
    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type",
        condition_expr="x > 10",
        vars_extract=["x"],
        persist_n=1,
        eval_interval_sec=30,
    )
    db_session.add_all([t, r])
    await db_session.commit()
    await db_session.refresh(r)
    return r


# ── _build_context ────────────────────────────────────────────────


async def test_build_context_all_vars(engine_with_cache, make_rule):
    engine, cache = engine_with_cache
    await cache.set("a", 1)
    await cache.set("b", 2)
    rule = make_rule(vars_extract=[])
    ctx = engine._build_context(rule)
    assert ctx == {"a": 1, "b": 2}


async def test_build_context_filters_by_vars_extract(engine_with_cache, make_rule):
    engine, cache = engine_with_cache
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)
    rule = make_rule(vars_extract=["a", "c"])
    ctx = engine._build_context(rule)
    assert ctx == {"a": 1, "c": 3}


async def test_build_context_empty_cache(engine_with_cache, make_rule):
    engine, _ = engine_with_cache
    ctx = engine._build_context(make_rule(vars_extract=[]))
    assert ctx == {}


def test_build_dispatch_context_returns_copy(engine_with_cache, make_rule):
    engine, _ = engine_with_cache
    eval_ctx = {"x": 1}
    out = engine._build_dispatch_context(make_rule(), eval_ctx)
    assert out == eval_ctx
    assert out is not eval_ctx


# ── reload_rules ──────────────────────────────────────────────────


async def test_reload_rules_loads_enabled_only(db_engine, db_session, make_rule, make_template):
    t = make_template(type="t1")
    r1 = make_rule(template_type="t1", name="r1", enabled=True)
    r2 = make_rule(template_type="t1", name="r2", enabled=False)
    db_session.add_all([t, r1, r2])
    await db_session.commit()

    engine = RuleEngine()
    await engine.reload_rules()
    assert r1.id in engine._rules
    assert r2.id not in engine._rules


async def test_reload_preserves_runtime_state(db_engine, db_session, make_rule, make_template):
    t = make_template(type="t1")
    r = make_rule(template_type="t1")
    db_session.add_all([t, r])
    await db_session.commit()

    engine = RuleEngine()
    await engine.reload_rules()
    # Mutate runtime state
    rt = engine._rules[r.id]
    rt.consecutive_match_count = 3
    rt.consecutive_eval_errors = 2

    # Reload — runtime state must survive
    await engine.reload_rules()
    rt2 = engine._rules[r.id]
    assert rt2.consecutive_match_count == 3
    assert rt2.consecutive_eval_errors == 2


async def test_reload_filter_excludes_disabled(db_engine, db_session, make_rule, make_template):
    """Two rules — one enabled, one disabled. Reload picks up only
    the enabled one."""
    t = make_template(type="t1")
    r_on = make_rule(template_type="t1", name="r_on", enabled=True)
    r_off = make_rule(template_type="t1", name="r_off", enabled=False)
    db_session.add_all([t, r_on, r_off])
    await db_session.commit()

    engine = RuleEngine()
    await engine.reload_rules()
    assert r_on.id in engine._rules
    assert r_off.id not in engine._rules


# ── _eval_rule paths ──────────────────────────────────────────────


async def test_eval_match_increments_persist_counter(db_engine, db_session, seeded_rule):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)  # x > 10 → True

    await engine.reload_rules()
    rt = engine._rules[seeded_rule.id]

    # Patch dispatcher.fire so the test stays isolated from channel I/O
    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(rt, now=0.0)

    # persist_n=1 → fire dispatched, then counter resets to 0
    assert rt.consecutive_match_count == 0
    fake_fire.assert_called_once()


async def test_eval_no_match_resets_counter(db_engine, db_session, make_rule, make_template):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 5)  # x > 10 → False

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type", condition_expr="x > 10",
        vars_extract=["x"], persist_n=2,
    )
    db_session.add_all([t, r])
    await db_session.commit()

    await engine.reload_rules()
    rt = engine._rules[r.id]
    rt.consecutive_match_count = 1  # in-progress ramp

    await engine._eval_rule(rt, now=0.0)

    assert rt.consecutive_match_count == 0


async def test_eval_persist_n_requires_consecutive_matches(db_engine, db_session, make_rule, make_template):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)  # x > 10 → True

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type", condition_expr="x > 10",
        vars_extract=["x"], persist_n=3,
    )
    db_session.add_all([t, r])
    await db_session.commit()

    await engine.reload_rules()
    rt = engine._rules[r.id]

    fake_fire = AsyncMock()
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        # First match — no fire (count=1, persist=3)
        await engine._eval_rule(rt, now=0.0)
        assert rt.consecutive_match_count == 1
        fake_fire.assert_not_called()

        # Second match — still no fire
        await engine._eval_rule(rt, now=1.0)
        assert rt.consecutive_match_count == 2
        fake_fire.assert_not_called()

        # Third match — fire, counter resets
        await engine._eval_rule(rt, now=2.0)
        assert rt.consecutive_match_count == 0
        fake_fire.assert_called_once()


async def test_eval_error_increments_error_counter(db_engine, db_session, make_rule, make_template):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type",
        condition_expr="unknown_function(1) > 10",  # FunctionNotDefined
        vars_extract=[],
        persist_n=1,
    )
    db_session.add_all([t, r])
    await db_session.commit()

    await engine.reload_rules()
    rt = engine._rules[r.id]

    await engine._eval_rule(rt, now=0.0)
    assert rt.consecutive_eval_errors == 1


async def test_a_missing_input_is_neither_an_error_nor_a_success(db_engine, db_session, make_rule, make_template):
    """sensor_drift_v1 was auto-disabled twice while the Tankbus namespace
    was absent from the cache: 'battery.cell_delta_mv > 50' raised a
    TypeError on the None binding, 50 ticks in a row. A gap in an input
    leaves the error counter where it is and the row says what is missing."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("thresh.cell_delta_warning_mv", 50)

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type",
        condition_expr="battery.cell_delta_mv > thresh.cell_delta_warning_mv",
        vars_extract=["battery.cell_delta_mv", "thresh.cell_delta_warning_mv"],
        persist_n=1,
    )
    db_session.add_all([t, r])
    await db_session.commit()

    await engine.reload_rules()
    rt = engine._rules[r.id]
    rt.consecutive_eval_errors = 3                  # a real error streak from before
    for _ in range(10):
        await engine._eval_rule(rt, now=0.0)
    assert rt.consecutive_eval_errors == 3          # untouched by the gap
    await db_session.refresh(r)
    assert (r.last_eval_error or "").startswith("missing input: battery.cell_delta_mv")


async def test_healed_missing_input_clears_the_row_error(db_engine, db_session, make_rule, make_template, monkeypatch):
    """A "missing input" gap is not counted, so the success path used to see
    consecutive_eval_errors == 0 and never cleared last_eval_error: rules kept
    showing "missing input" long after the variable came back (2026-11-14,
    containers_down_v1 matched and fired with the stale text still on it).
    The repeated gap must also not rewrite the same row every tick."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(template_type="r_type", condition_expr="sensor.x > 10", vars_extract=["sensor.x"], persist_n=1)
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]

    writes = []
    original = engine._record_eval_error

    async def counting(rt_, error, **kw):
        writes.append(error)
        await original(rt_, error, **kw)

    monkeypatch.setattr(engine, "_record_eval_error", counting)
    for _ in range(5):
        await engine._eval_rule(rt, now=0.0)          # x missing
    await db_session.refresh(r)
    assert (r.last_eval_error or "").startswith("missing input: sensor.x")
    assert rt.consecutive_eval_errors == 0

    await cache.set("sensor.x", 5)
    await engine._eval_rule(rt, now=0.0)              # data is back
    await fresh(db_session)
    await db_session.refresh(r)
    assert r.last_eval_error is None
    assert rt.last_eval_error is None

    assert writes[0].startswith("missing input") and writes[-1] is None


async def test_repeated_missing_input_writes_the_row_once(db_engine, db_session, make_rule, make_template, monkeypatch):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(template_type="r_type", condition_expr="x > 10", vars_extract=["x"], persist_n=1)
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]

    from app.core import engine as engine_module
    sessions = []
    real_get_session = engine_module.get_session

    async def tracking_get_session():
        sessions.append(1)
        async for s in real_get_session():
            yield s

    await engine._record_eval_error(rt, "missing input: x")
    monkeypatch.setattr(engine_module, "get_session", tracking_get_session)
    for _ in range(5):
        await engine._record_eval_error(rt, "missing input: x")
    assert sessions == []                             # unchanged → no write


async def test_eval_success_resets_error_counter(db_engine, db_session, make_rule, make_template):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 5)

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type", condition_expr="x > 10",
        vars_extract=["x"], persist_n=1,
    )
    db_session.add_all([t, r])
    await db_session.commit()

    await engine.reload_rules()
    rt = engine._rules[r.id]
    rt.consecutive_eval_errors = 3  # in-progress error ramp

    await engine._eval_rule(rt, now=0.0)
    # Eval succeeded (no match) → error counter reset
    assert rt.consecutive_eval_errors == 0


# ── _tick ─────────────────────────────────────────────────────────


async def test_tick_evaluates_due_rules(db_engine, db_session, make_rule, make_template):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type", condition_expr="x > 10",
        vars_extract=["x"], persist_n=1, eval_interval_sec=30,
    )
    db_session.add_all([t, r])
    await db_session.commit()

    await engine.reload_rules()
    rt = engine._rules[r.id]
    rt.next_eval_at = 0.0  # always due

    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._tick()

    fake_fire.assert_called_once()
    # next_eval_at advanced by eval_interval_sec
    assert rt.next_eval_at > 0


async def test_tick_skips_not_due_rules(db_engine, db_session, make_rule, make_template):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type", condition_expr="x > 10",
        vars_extract=["x"], persist_n=1, eval_interval_sec=30,
    )
    db_session.add_all([t, r])
    await db_session.commit()

    import time as _time

    await engine.reload_rules()
    rt = engine._rules[r.id]
    # Push next_eval_at far past the current monotonic clock — the
    # value must be ABOVE _time.monotonic() (which is uptime-based,
    # not 0).
    rt.next_eval_at = _time.monotonic() + 1_000_000.0

    fake_fire = AsyncMock()
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._tick()
    fake_fire.assert_not_called()


async def test_tick_isolates_rule_failures(db_engine, db_session, make_rule, make_template):
    """One rule's exception must not stop other due rules from running."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)

    t = make_template(type="r_type", min_repeat_min=0)
    r1 = make_rule(template_type="r_type", condition_expr="x > 10", name="r1", persist_n=1)
    r2 = make_rule(template_type="r_type", condition_expr="x > 10", name="r2", persist_n=1)
    db_session.add_all([t, r1, r2])
    await db_session.commit()

    await engine.reload_rules()
    for rt in engine._rules.values():
        rt.next_eval_at = 0.0

    # Make r1's eval blow up; r2 should still be evaluated
    real_eval = engine._eval_rule
    call_count = {"n": 0}

    async def flaky_eval(rt, *, now, **kw):
        call_count["n"] += 1
        if rt.rule.name == "r1":
            raise RuntimeError("boom")
        await real_eval(rt, now=now, **kw)

    with patch.object(engine, "_eval_rule", side_effect=flaky_eval):
        await engine._tick()

    # Both rules attempted
    assert call_count["n"] == 2


# ── Lifecycle ─────────────────────────────────────────────────────


async def test_start_idempotent(db_engine):
    engine = RuleEngine(base_tick_sec=0.01)
    await engine.start()
    task = engine._task
    await engine.start()  # second start — no-op
    assert engine._task is task
    await engine.stop()


async def test_stop_clears_task(db_engine):
    engine = RuleEngine(base_tick_sec=0.01)
    await engine.start()
    assert engine._task is not None
    await engine.stop()
    assert engine._task is None


def test_get_engine_singleton():
    a = get_engine()
    b = get_engine()
    assert a is b


# ── _RuleRuntime construction ─────────────────────────────────────


def test_runtime_default_state(make_rule):
    rt = _RuleRuntime(rule=make_rule())
    assert rt.next_eval_at == 0.0
    assert rt.consecutive_match_count == 0
    assert rt.last_match_at is None
    assert rt.consecutive_eval_errors == 0


# ── Auto-disable meta-alert (silent-decay guard) ──────────────────


# SQLite-only: under MySQL's REPEATABLE READ, db_session's snapshot doesn't see
# the engine's committed auto-disable within the same read transaction (V13 CI).
@pytest.mark.sqlite
async def test_auto_disable_fires_meta_alert(
    db_engine, db_session, make_rule, make_template
):
    """At eval_error_disable_threshold consecutive errors the rule is
    disabled in DB AND the engine fires rule_auto_disabled about it."""
    from app.config import get_settings

    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache  # cache empty → the rule's function is unknown → eval error

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type",
        condition_expr="missing_fn(1) > 1",  # a real error (RL-05: a missing name is no data)
        vars_extract=["missing_var"],
        persist_n=1,
    )
    db_session.add_all([t, r])
    await db_session.commit()
    await db_session.refresh(r)

    await engine.reload_rules()
    rt = engine._rules[r.id]

    settings = get_settings()
    old_threshold = settings.eval_error_disable_threshold
    object.__setattr__(settings, "eval_error_disable_threshold", 3)
    try:
        fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": True})())
        with patch("app.core.engine.dispatcher_module.fire", fake_fire):
            for i in range(3):
                await engine._eval_rule(rt, now=float(i))
    finally:
        object.__setattr__(settings, "eval_error_disable_threshold", old_threshold)

    # Rule disabled in DB (capture the id BEFORE expire_all — an
    # expired instance can't lazy-load in async context)
    rid = r.id
    db_session.expire_all()
    row = (await db_session.execute(select(Rule).where(Rule.id == rid))).scalar_one()
    assert row.enabled is False

    # Exactly one meta-fire, with the right envelope
    fake_fire.assert_called_once()
    env = fake_fire.call_args.args[0]
    assert env.type == "rule_auto_disabled"
    assert env.source == "engine-meta"
    assert env.context["rule_name"] == r.name
    assert env.context["rule_id"] == r.id
    assert env.context["threshold"] == 3
    assert "missing_fn" in env.context["error"]


async def test_auto_disabled_rule_removed_from_indexes_and_not_evaluated(
    db_engine, db_session, make_rule, make_template
):
    """F10: an auto-disabled rule must leave every runtime index so a
    later tick can neither evaluate nor re-fire it."""
    from app.config import get_settings

    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache  # empty → eval error every tick

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type",
        condition_expr="missing_fn(1) > 1",  # a real error (RL-05: a missing name is no data)
        vars_extract=["missing_var"],
        persist_n=1,
    )
    db_session.add_all([t, r])
    await db_session.commit()
    await db_session.refresh(r)

    await engine.reload_rules()
    rt = engine._rules[r.id]

    settings = get_settings()
    old_threshold = settings.eval_error_disable_threshold
    object.__setattr__(settings, "eval_error_disable_threshold", 3)
    try:
        fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": True})())
        with patch("app.core.engine.dispatcher_module.fire", fake_fire):
            for i in range(3):  # reach the disable threshold
                await engine._eval_rule(rt, now=float(i))
            # Gone from every index.
            assert r.id not in engine._rules
            assert r.name not in engine._by_name
            assert r.name not in engine._last_truthy
            # A later tick evaluates nothing (and never re-fires the rule).
            with patch.object(engine, "_eval_rule", AsyncMock()) as spy:
                await engine._tick()
                spy.assert_not_called()
    finally:
        object.__setattr__(settings, "eval_error_disable_threshold", old_threshold)


async def test_tick_skips_runtime_disabled_in_place(engine_with_cache):
    """F10 guard: even if a disabled runtime is still indexed, _tick must
    not evaluate it."""
    engine, _cache = engine_with_cache
    rule = type("R", (), {"id": 1, "name": "rx", "enabled": False,
                          "eval_interval_sec": 10})()
    rt = _RuleRuntime(rule=rule, next_eval_at=0.0)
    engine._rules[1] = rt
    with patch.object(engine, "_eval_rule", AsyncMock()) as spy:
        await engine._tick()
        spy.assert_not_called()


async def test_no_meta_alert_below_threshold(
    db_engine, db_session, make_rule, make_template
):
    from app.config import get_settings

    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type",
        condition_expr="missing_fn(1) > 1",  # a real error (RL-05: a missing name is no data)
        vars_extract=["missing_var"],
        persist_n=1,
    )
    db_session.add_all([t, r])
    await db_session.commit()
    await db_session.refresh(r)

    await engine.reload_rules()
    rt = engine._rules[r.id]

    settings = get_settings()
    old_threshold = settings.eval_error_disable_threshold
    object.__setattr__(settings, "eval_error_disable_threshold", 3)
    try:
        fake_fire = AsyncMock()
        with patch("app.core.engine.dispatcher_module.fire", fake_fire):
            for i in range(2):  # one below threshold
                await engine._eval_rule(rt, now=float(i))
    finally:
        object.__setattr__(settings, "eval_error_disable_threshold", old_threshold)

    fake_fire.assert_not_called()
    rid = r.id
    db_session.expire_all()
    row = (await db_session.execute(select(Rule).where(Rule.id == rid))).scalar_one()
    assert row.enabled is True


# ── Inhibition (storm correlation) ────────────────────────────────


async def _seed_inhibition_pair(db_session, make_rule, make_template):
    """Inhibitor rule 'storm_root' (y > 0) + target rule inhibited by
    it (x > 10). Both persist_n=1, same eval interval."""
    t1 = make_template(type="root_type", min_repeat_min=0)
    t2 = make_template(type="dep_type", min_repeat_min=0)
    root = make_rule(
        name="storm_root", template_type="root_type",
        condition_expr="y > 0", vars_extract=["y"], persist_n=1,
        eval_interval_sec=10,
    )
    dep = make_rule(
        name="dep_rule", template_type="dep_type",
        condition_expr="x > 10", vars_extract=["x"], persist_n=1,
        inhibited_by=["storm_root"],
    )
    db_session.add_all([t1, t2, root, dep])
    await db_session.commit()
    await db_session.refresh(root)
    await db_session.refresh(dep)
    return root, dep


async def test_active_inhibitor_suppresses_dependent(
    db_engine, db_session, make_rule, make_template
):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    root, dep = await _seed_inhibition_pair(db_session, make_rule, make_template)
    await cache.set("y", 1)   # root active
    await cache.set("x", 99)  # dep would fire

    await engine.reload_rules()
    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(engine._rules[root.id], now=100.0)
        await engine._eval_rule(engine._rules[dep.id], now=101.0)

    envs = [c.args[0] for c in fake_fire.call_args_list]
    by_type = {e.type: e for e in envs}
    assert by_type["root_type"].inhibited_by_active is None
    assert by_type["dep_type"].inhibited_by_active == "storm_root"


async def test_stale_inhibitor_does_not_suppress(
    db_engine, db_session, make_rule, make_template
):
    """Inhibitor last truthy far outside its grace window (2×interval+5)."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    root, dep = await _seed_inhibition_pair(db_session, make_rule, make_template)
    await cache.set("y", 1)
    await cache.set("x", 99)

    await engine.reload_rules()
    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(engine._rules[root.id], now=100.0)
        # 10s interval → grace 25s; evaluate dep 60s later
        await engine._eval_rule(engine._rules[dep.id], now=160.0)

    envs = [c.args[0] for c in fake_fire.call_args_list]
    dep_env = next(e for e in envs if e.type == "dep_type")
    assert dep_env.inhibited_by_active is None


async def test_unknown_inhibitor_ignored(
    db_engine, db_session, make_rule, make_template
):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    t = make_template(type="dep_type", min_repeat_min=0)
    dep = make_rule(
        name="dep_rule2", template_type="dep_type",
        condition_expr="x > 10", vars_extract=["x"], persist_n=1,
        inhibited_by=["never_existed"],
    )
    db_session.add_all([t, dep])
    await db_session.commit()
    await db_session.refresh(dep)
    await cache.set("x", 99)

    await engine.reload_rules()
    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(engine._rules[dep.id], now=100.0)

    env = fake_fire.call_args.args[0]
    assert env.inhibited_by_active is None


# ── throttled re-fires are not logged more than once per window ─────────


async def test_throttled_refires_are_dropped_until_window_ends(db_engine, db_session, seeded_rule):
    """A condition that stays true fires once, gets one 'throttled' row,
    and is then dropped silently while the template window is open
    (2026-09-09: 238 log rows/day for a battery stuck at 'Critic')."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)
    await engine.reload_rules()
    rt = engine._rules[seeded_rule.id]

    delivered = type("R", (), {"dispatched": True, "suppressed_reason": None})()
    throttled = type("R", (), {"dispatched": False, "suppressed_reason": "throttled"})()
    fake_fire = AsyncMock(side_effect=[delivered, throttled, throttled, throttled])
    with patch("app.core.engine.dispatcher_module.fire", fake_fire), \
         patch.object(engine, "_template_throttled", AsyncMock(return_value=True)):
        for _ in range(4):
            await engine._eval_rule(rt, now=0.0)
    # 1 delivered + 1 throttled row; the remaining two matches are dropped
    assert fake_fire.call_count == 2
    assert rt.throttled_since_dispatch is True


async def test_refire_resumes_when_window_closes(db_engine, db_session, seeded_rule):
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)
    await engine.reload_rules()
    rt = engine._rules[seeded_rule.id]
    rt.throttled_since_dispatch = True

    delivered = type("R", (), {"dispatched": True, "suppressed_reason": None})()
    fake_fire = AsyncMock(return_value=delivered)
    with patch("app.core.engine.dispatcher_module.fire", fake_fire), \
         patch.object(engine, "_template_throttled", AsyncMock(return_value=False)):
        await engine._eval_rule(rt, now=0.0)
    fake_fire.assert_called_once()
    assert rt.throttled_since_dispatch is False


# ── A17: transition semantics (persist streak + inhibition) ───────


async def test_missing_input_breaks_persist_streak(
    db_engine, db_session, make_rule, make_template
):
    """A gap (missing input) mid-ramp must reset the persist streak — N
    consecutive confirmations can't span a tick with no data (audit A17)."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    await cache.set("x", 99)  # x > 10 → True

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type", condition_expr="x > 10",
        vars_extract=["x"], persist_n=3,
    )
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]

    fake_fire = AsyncMock()
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(rt, now=0.0)  # count 1
        await engine._eval_rule(rt, now=1.0)  # count 2
        assert rt.consecutive_match_count == 2

        cache.clear(only={"x"})               # input gap → missing
        await engine._eval_rule(rt, now=2.0)
        assert rt.consecutive_match_count == 0  # streak broken

        await cache.set("x", 99)
        await engine._eval_rule(rt, now=3.0)  # starts over at 1, not 3
        assert rt.consecutive_match_count == 1
        fake_fire.assert_not_called()


async def test_eval_error_breaks_persist_streak(
    db_engine, db_session, make_rule, make_template
):
    """An eval error is an unknown transition — it must reset the persist
    streak (while still counting toward the error/auto-disable path)."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache

    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(
        template_type="r_type", condition_expr="undefined_fn(1) > 10",
        vars_extract=[], persist_n=2,
    )
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]
    rt.consecutive_match_count = 1  # pretend mid-ramp

    await engine._eval_rule(rt, now=0.0)
    assert rt.consecutive_match_count == 0   # streak broken by the error
    assert rt.consecutive_eval_errors == 1   # error path still ran


async def test_false_inhibitor_stops_suppressing_immediately(
    db_engine, db_session, make_rule, make_template
):
    """An inhibitor that evaluates definitively false must stop inhibiting
    its dependents at once — not linger for the whole grace window, which
    only exists to tolerate missed ticks (audit A17)."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    root, dep = await _seed_inhibition_pair(db_session, make_rule, make_template)
    await cache.set("y", 1)
    await cache.set("x", 99)
    await engine.reload_rules()

    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(engine._rules[root.id], now=100.0)  # root truthy
        await cache.set("y", 0)                                     # root now false
        await engine._eval_rule(engine._rules[root.id], now=101.0)  # false → clear marker
        await engine._eval_rule(engine._rules[dep.id], now=102.0)   # within grace, but...

    envs = [c.args[0] for c in fake_fire.call_args_list]
    dep_env = next(e for e in envs if e.type == "dep_type")
    assert dep_env.inhibited_by_active is None  # not suppressed anymore


async def test_missing_inhibitor_keeps_suppressing_within_grace(
    db_engine, db_session, make_rule, make_template
):
    """A missed tick (inhibitor input gone) keeps the inhibition alive for
    the grace window — the gap behavior A17 deliberately preserves."""
    cache = StateCache()
    engine = RuleEngine()
    engine._cache = cache
    root, dep = await _seed_inhibition_pair(db_session, make_rule, make_template)
    await cache.set("y", 1)
    await cache.set("x", 99)
    await engine.reload_rules()

    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(engine._rules[root.id], now=100.0)  # root truthy
        cache.clear(only={"y"})                                     # inhibitor input gone
        await engine._eval_rule(engine._rules[root.id], now=105.0)  # missing → marker kept
        await engine._eval_rule(engine._rules[dep.id], now=110.0)   # 10s < 25s grace

    envs = [c.args[0] for c in fake_fire.call_args_list]
    dep_env = next(e for e in envs if e.type == "dep_type")
    assert dep_env.inhibited_by_active == "storm_root"


async def test_reload_resets_streak_on_condition_change(
    db_engine, db_session, make_rule, make_template
):
    """A reconfigured condition starts fresh — a streak counted against the
    old expression is meaningless for the new one (audit A17)."""
    t = make_template(type="t1")
    r = make_rule(template_type="t1", condition_expr="x > 20")
    db_session.add_all([t, r])
    await db_session.commit()

    engine = RuleEngine()
    await engine.reload_rules()
    rt = engine._rules[r.id]
    rt.consecutive_match_count = 3
    engine._last_truthy[r.name] = 123.0
    # Simulate the live runtime holding the OLD expression: the next reload
    # reads the DB's current expression ("x > 20") and must see it as
    # reconfigured vs this stale in-memory one. (Mutating the DB mid-test
    # isn't visible across the shared-connection SQLite fixture, so we flip
    # the in-memory side instead — same comparison either way.)
    rt.rule.condition_expr = "x > 10"

    await engine.reload_rules()

    rt2 = engine._rules[r.id]
    assert rt2.consecutive_match_count == 0
    assert r.name not in engine._last_truthy


async def test_reload_preserves_streak_when_condition_unchanged(
    db_engine, db_session, make_rule, make_template
):
    """Counterpart to the reconfigured case: an unchanged expression keeps
    its streak across reload (no H-1 regression)."""
    t = make_template(type="t1")
    r = make_rule(template_type="t1", condition_expr="x > 10")
    db_session.add_all([t, r])
    await db_session.commit()

    engine = RuleEngine()
    await engine.reload_rules()
    engine._rules[r.id].consecutive_match_count = 4

    await engine.reload_rules()  # no change
    assert engine._rules[r.id].consecutive_match_count == 4
