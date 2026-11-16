"""B-05: a rule disabled/reconfigured mid-tick must not fire from stale work.

A tick captures the set of due runtimes and then evaluates them across several
awaits. ``reload_rules`` can run during those awaits (an admin toggling a rule),
swapping ``self._rules`` for fresh runtimes and dropping disabled rules. The
tick's captured runtime is then stale, so evaluating/firing it would deliver a
notification for a rule that is no longer enabled. The engine re-checks runtime
identity both before evaluating a due rule and again at the fire boundary.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.core.engine import RuleEngine
from app.core.state_cache import StateCache


def _engine(cache: StateCache) -> RuleEngine:
    engine = RuleEngine()
    engine._cache = cache
    return engine


async def _seed_rule(db_session, make_rule, make_template, name="rule_x"):
    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(template_type="r_type", condition_expr="x > 10",
                  vars_extract=["x"], persist_n=1, eval_interval_sec=30, name=name)
    db_session.add_all([t, r])
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def test_fire_boundary_rejects_rule_disabled_during_eval(
    db_engine, db_session, make_rule, make_template
):
    """Guard at the fire boundary: a reload that drops the rule between the
    match and the dispatch must stop the fire (negative control: without the
    re-check the fire lands)."""
    cache = StateCache()
    await cache.set("x", 99)  # x > 10 → match, persist_n=1 → would fire
    engine = _engine(cache)
    rule = await _seed_rule(db_session, make_rule, make_template)
    await engine.reload_rules()
    rt = engine._rules[rule.id]

    # Simulate a concurrent reload disabling the rule during _eval_rule:
    # _persist_state is awaited right before the fire threshold check.
    async def drop_during_persist(rt_arg):
        engine._rules.pop(rt_arg.rule.id, None)

    engine._persist_state = drop_during_persist  # type: ignore[method-assign]

    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": False})())
    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._eval_rule(rt, now=0.0)

    fake_fire.assert_not_called()


async def test_tick_skips_rule_disabled_earlier_in_tick(
    db_engine, db_session, make_rule, make_template
):
    """Guard at the tick loop: evaluating an earlier due rule disables a later
    one; the later rule must not fire from the already-captured due list."""
    cache = StateCache()
    await cache.set("x", 99)
    engine = _engine(cache)

    t = make_template(type="r_type", min_repeat_min=0)
    r_a = make_rule(template_type="r_type", condition_expr="x > 10",
                    vars_extract=["x"], persist_n=1, eval_interval_sec=30, name="rule_a")
    r_b = make_rule(template_type="r_type", condition_expr="x > 10",
                    vars_extract=["x"], persist_n=1, eval_interval_sec=30, name="rule_b")
    db_session.add_all([t, r_a, r_b])
    await db_session.commit()
    await db_session.refresh(r_a)
    await db_session.refresh(r_b)

    await engine.reload_rules()
    # Deterministic order: A evaluated before B; both due now.
    engine._rules = {r_a.id: engine._rules[r_a.id], r_b.id: engine._rules[r_b.id]}
    for rt in engine._rules.values():
        rt.next_eval_at = 0.0

    orig_eval = engine._eval_rule

    async def eval_then_disable_b(rt, *, now):
        if rt.rule.id == r_a.id:
            engine._rules.pop(r_b.id, None)  # admin disables B mid-tick
        return await orig_eval(rt, now=now)

    engine._eval_rule = eval_then_disable_b  # type: ignore[method-assign]

    fired: list[int] = []

    async def fake_fire(env, s):
        fired.append(env.rule_id)
        return type("R", (), {"dispatched": True, "suppressed_reason": None})()

    with patch("app.core.engine.dispatcher_module.fire", fake_fire):
        await engine._tick()

    assert r_a.id in fired
    assert r_b.id not in fired  # stale (disabled) rule must not fire


async def test_is_current_detects_stale_and_disabled(
    db_engine, db_session, make_rule, make_template
):
    cache = StateCache()
    engine = _engine(cache)
    rule = await _seed_rule(db_session, make_rule, make_template)
    await engine.reload_rules()
    rt = engine._rules[rule.id]
    assert engine._is_current(rt) is True

    # A reload replaces the runtime object → the old one is stale.
    await engine.reload_rules()
    assert engine._is_current(rt) is False

    # A live-but-disabled runtime is not current either.
    live = engine._rules[rule.id]
    live.rule.enabled = False
    assert engine._is_current(live) is False
