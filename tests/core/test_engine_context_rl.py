"""Rules review 2026-11-18 (RL-03, RL-12): what a rule sees, and the engine
writing ``rule_state`` only when something changed."""
from __future__ import annotations

from app.core import engine as engine_module
from app.core.engine import RuleEngine, _RuleRuntime, rule_context
from app.core.state_cache import StateCache


async def _cache(**values):
    cache = StateCache()
    for name, value in values.items():
        await cache.set(name.replace("__", "."), value, source_kind="mqtt", stale_after_sec=300)
    return cache


async def test_variables_read_by_the_conditions_join_vars_extract():
    cache = await _cache(a__x=1, b__y=2, c__z=3)
    ctx = rule_context(cache, ["c.z"], "a.x > 0", "b.y < 5")
    assert ctx == {"a.x": 1, "b.y": 2, "c.z": 3}


async def test_an_empty_vars_extract_still_means_every_variable():
    cache = await _cache(a__x=1, b__y=2)
    assert rule_context(cache, [], "a.x > 0") == {"a.x": 1, "b.y": 2}


async def test_stale_variables_stay_out():
    cache = StateCache()
    await cache.set("a.x", 1, source_kind="mqtt", stale_after_sec=1)
    cache.get("a.x").ts -= 100          # last update 100 s ago
    assert rule_context(cache, ["a.x"], "a.x > 0") == {}


async def test_a_rule_whose_vars_extract_forgot_a_variable_now_matches(db_engine, db_session, make_rule, make_template):
    """Before RL-03 ``a.x`` was missing from the context → "missing input"
    for ever."""
    engine = RuleEngine()
    engine._cache = await _cache(a__x=50, other__v=1)
    t = make_template(type="rl03", min_repeat_min=0)
    r = make_rule(template_type="rl03", condition_expr="a.x > 10", vars_extract=["other.v"], persist_n=2)
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]
    await engine._eval_rule(rt, now=0.0)
    assert rt.consecutive_match_count == 1 and rt.last_eval_error is None


async def test_persist_state_skips_an_unchanged_row(monkeypatch, make_rule):
    rt = _RuleRuntime(rule=make_rule(), consecutive_match_count=0, recovery_match_count=0, state_epoch=3)
    rt.persisted = (0, 0, 3)

    def _no_db():
        raise AssertionError("rule_state written although nothing changed")
    monkeypatch.setattr(engine_module, "get_session", _no_db)
    await RuleEngine()._persist_state(rt)


async def test_an_idle_incident_rule_writes_rule_state_once(db_engine, db_session, make_rule, make_template, monkeypatch):
    """Before RL-12 every evaluation of an incident rule wrote the row."""
    engine = RuleEngine()
    engine._cache = await _cache(a__x=1)
    t = make_template(type="rl12", min_repeat_min=0)
    r = make_rule(template_type="rl12", condition_expr="a.x > 10", vars_extract=["a.x"], incident_enabled=True)
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]

    calls = []
    real = engine_module.get_session

    def counting():
        calls.append(1)
        return real()
    monkeypatch.setattr(engine_module, "get_session", counting)
    for i in range(5):
        await engine._eval_rule(rt, now=float(i))
    # At most the state row and the first run-state transition (RL-32).
    assert len(calls) <= 2
