"""Rules review, stage 3: run-state history (RL-32) and "what if" validate (RL-31)."""
from __future__ import annotations

from sqlalchemy import select

from app.core.engine import RuleEngine
from app.core.state_cache import StateCache
from app.db.models import Rule, RuleTransition
from tests._db import fresh


async def _cache(**values):
    cache = StateCache()
    for name, value in values.items():
        await cache.set(name.replace("__", "."), value, source_kind="mqtt", stale_after_sec=300)
    return cache


async def _states(db_session, rule_id):
    await fresh(db_session)
    rows = (await db_session.execute(
        select(RuleTransition).where(RuleTransition.rule_id == rule_id).order_by(RuleTransition.id)
    )).scalars().all()
    return [(r.from_state, r.to_state) for r in rows]


async def _setup(db_session, make_rule, make_template, cache, **rule_kw):
    engine = RuleEngine()
    engine._cache = cache
    t = make_template(type="rl32", min_repeat_min=0)
    r = make_rule(template_type="rl32", **rule_kw)
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    return engine, r.id


async def test_a_plain_rule_goes_inactive_pending_firing_inactive(db_engine, db_session, make_rule, make_template):
    cache = await _cache(a__x=1)
    engine, rid = await _setup(db_session, make_rule, make_template, cache,
                             condition_expr="a.x > 10", persist_n=3)
    rt = engine._rules[rid]
    for value in (1, 1, 50, 50, 50, 50, 50, 1, 1):
        await cache.set("a.x", value, source_kind="mqtt", stale_after_sec=300)
        await engine._eval_rule(rt, now=0.0)
    assert await _states(db_session, rid) == [
        (None, "inactive"), ("inactive", "pending"), ("pending", "firing"), ("firing", "inactive"),
    ]
    row = (await db_session.execute(select(Rule).where(Rule.id == rid))).scalar_one()
    assert row.run_state == "inactive"
    assert row.last_true_at is not None
    assert row.run_state_since >= row.last_true_at


async def test_no_data_and_error_are_states_with_their_reason(db_engine, db_session, make_rule, make_template):
    cache = await _cache()
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="a.x / 0 > 1")
    rt = engine._rules[rid]
    await engine._eval_rule(rt, now=0.0)                       # a.x missing
    await cache.set("a.x", 5, source_kind="mqtt", stale_after_sec=300)
    await engine._eval_rule(rt, now=1.0)                       # division by zero
    await fresh(db_session)
    rows = (await db_session.execute(select(RuleTransition).where(RuleTransition.rule_id == rid)
                                      .order_by(RuleTransition.id))).scalars().all()
    assert [x.to_state for x in rows] == ["no_data", "error"]
    assert rows[0].detail.startswith("missing input: a.x")
    assert "ZeroDivisionError" in rows[1].detail


async def test_an_incident_stays_firing_inside_the_hysteresis_band(db_engine, db_session, make_rule, make_template):
    cache = await _cache(a__x=90)
    engine, rid = await _setup(db_session, make_rule, make_template, cache,
                             condition_expr="a.x > 80", incident_enabled=True, recovery_expr="a.x < 75")
    rt = engine._rules[rid]
    for value in (90, 78, 78, 70):
        await cache.set("a.x", value, source_kind="mqtt", stale_after_sec=300)
        await engine._eval_rule(rt, now=0.0)
    assert await _states(db_session, rid) == [(None, "firing"), ("firing", "inactive")]


async def test_the_engine_bookkeeping_does_not_touch_updated_at(db_engine, db_session, make_rule, make_template):
    cache = await _cache(a__x=50)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="a.x > 10")
    before = (await db_session.execute(select(Rule.updated_at).where(Rule.id == rid))).scalar_one()
    await engine._eval_rule(engine._rules[rid], now=0.0)
    await fresh(db_session)
    after = (await db_session.execute(select(Rule.updated_at, Rule.run_state).where(Rule.id == rid))).one()
    assert after == (before, "firing")


async def test_a_flapping_rule_is_capped_and_says_how_much_it_skipped(db_engine, db_session, make_rule, make_template, monkeypatch):
    monkeypatch.setattr(RuleEngine, "TRANSITIONS_PER_HOUR", 4)
    cache = await _cache(a__x=1)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="a.x > 10", persist_n=5)
    rt = engine._rules[rid]
    for i in range(10):
        await cache.set("a.x", 50 if i % 2 else 1, source_kind="mqtt", stale_after_sec=300)
        await engine._eval_rule(rt, now=float(i))
    assert len(await _states(db_session, rid)) == 4
    rt.transition_times.clear()                                # an hour later
    await cache.set("a.x", 1, source_kind="mqtt", stale_after_sec=300)
    await engine._eval_rule(rt, now=20.0)
    await fresh(db_session)
    last = (await db_session.execute(select(RuleTransition).where(RuleTransition.rule_id == rid)
                                      .order_by(RuleTransition.id.desc()).limit(1))).scalar_one()
    assert (last.from_state, last.to_state) == ("pending", "inactive")
    assert last.detail.startswith("6 changes not recorded")


async def test_transitions_endpoint_newest_first(db_client, admin_key, db_session, make_rule, make_template):
    from app.utils.time import utc_now
    t = make_template(type="rl32api", min_repeat_min=0)
    r = make_rule(template_type="rl32api", condition_expr="x > 1")
    db_session.add_all([t, r])
    await db_session.commit()
    db_session.add_all([RuleTransition(rule_id=r.id, at=utc_now(), from_state=None, to_state="inactive"),
                        RuleTransition(rule_id=r.id, at=utc_now(), from_state="inactive", to_state="pending")])
    await db_session.commit()
    h = {"X-API-Key": admin_key}
    body = (await db_client.get(f"/v1/rules/{r.id}/transitions", headers=h)).json()
    assert [x["to_state"] for x in body] == ["pending", "inactive"]
    assert body[0]["at"].endswith("Z")
    assert (await db_client.get("/v1/rules/999999/transitions", headers=h)).status_code == 404


async def test_validate_with_a_what_if_context(db_client, admin_key):
    from app.core.state_cache import get_state_cache, reset_state_cache_for_tests
    reset_state_cache_for_tests()
    await get_state_cache().set("soc", 42.0, source_kind="mqtt", stale_after_sec=300)
    h = {"X-API-Key": admin_key}
    live = (await db_client.post("/v1/rules/validate", json={"condition_expr": "soc < 20"}, headers=h)).json()
    what_if = (await db_client.post("/v1/rules/validate", json={"condition_expr": "soc < 20", "context": {"soc": 12}},
                                    headers=h)).json()
    missing = (await db_client.post("/v1/rules/validate", json={"condition_expr": "soc < 20", "context": {"soc": None}},
                                    headers=h)).json()
    assert (live["result"], what_if["result"]) == (False, True)
    assert missing["ok"] is False
    assert missing["error"].startswith("missing input")
    # The live value is still reported next to the what-if result.
    assert what_if["referenced_vars"][0]["live_value"] == 42.0
    too_big = await db_client.post("/v1/rules/validate", headers=h,
                                   json={"condition_expr": "soc < 20", "context": {"s": "x" * 70000}})
    assert too_big.status_code == 422
    reset_state_cache_for_tests()


# ── 2026-11-18 review of stage 3 (RV-02 … RV-05) ──────────────────


async def _db_state(db_session, rid):
    await fresh(db_session)
    return (await db_session.execute(select(Rule.run_state).where(Rule.id == rid))).scalar_one()


async def test_the_history_budget_never_freezes_the_current_state(db_engine, db_session, make_rule, make_template, monkeypatch):
    """RV-02: past the budget the API kept showing an old state."""
    monkeypatch.setattr(RuleEngine, "TRANSITIONS_PER_HOUR", 2)
    cache = await _cache(a__x=1)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="a.x > 10", persist_n=5)
    rt = engine._rules[rid]
    for value in (1, 50, 1):
        await cache.set("a.x", value, source_kind="mqtt", stale_after_sec=300)
        await engine._eval_rule(rt, now=0.0)
    assert len(await _states(db_session, rid)) == 2
    assert await _db_state(db_session, rid) == "inactive"


async def test_a_failed_write_is_retried_and_spends_no_budget(db_engine, db_session, make_rule, make_template, monkeypatch):
    """RV-03: a write that failed once was never tried again."""
    from app.core import engine as engine_module
    cache = await _cache(a__x=50)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="a.x > 10", persist_n=5)
    rt = engine._rules[rid]
    real = engine_module.get_session_factory
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database gone for a moment")
        return real()
    monkeypatch.setattr(engine_module, "get_session_factory", flaky)
    await engine._eval_rule(rt, now=0.0)
    assert await _states(db_session, rid) == []
    assert len(rt.transition_times) == 0
    await engine._eval_rule(rt, now=1.0)                       # same state: written now
    assert await _states(db_session, rid) == [(None, "pending")]
    assert await _db_state(db_session, rid) == "pending"


async def test_a_new_condition_does_not_inherit_firing(db_engine, db_session, make_rule, make_template):
    """RV-04: an edited rule kept the old expression's "firing"."""
    from sqlalchemy import update
    cache = await _cache(a__x=50)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="a.x > 10", persist_n=3)
    for _ in range(3):
        await engine._eval_rule(engine._rules[rid], now=0.0)
    assert engine._rules[rid].run_state == "firing"
    await db_session.execute(update(Rule).where(Rule.id == rid).values(condition_expr="a.x > 40", state_epoch=Rule.state_epoch + 1))
    await db_session.commit()
    await engine.reload_rules()
    await engine._eval_rule(engine._rules[rid], now=1.0)
    assert engine._rules[rid].run_state == "pending"
    await fresh(db_session)
    last = (await db_session.execute(select(RuleTransition).where(RuleTransition.rule_id == rid)
                                      .order_by(RuleTransition.id.desc()).limit(1))).scalar_one()
    assert (last.from_state, last.to_state, last.detail) == ("firing", "pending", "rule changed")


async def test_an_open_incident_is_firing_again_after_a_gap_in_the_data(db_engine, db_session, make_rule, make_template):
    """RV-05: the streak restarts after no_data, the incident is still open."""
    cache = await _cache(a__x=50)
    engine, rid = await _setup(db_session, make_rule, make_template, cache,
                               condition_expr="a.x > 10", persist_n=3, incident_enabled=True)
    rt = engine._rules[rid]
    for _ in range(3):
        await engine._eval_rule(rt, now=0.0)
    assert rt.run_state == "firing"
    await cache.set("a.x", None, source_kind="mqtt", stale_after_sec=300)
    await engine._eval_rule(rt, now=1.0)
    assert rt.run_state == "no_data"
    await cache.set("a.x", 50, source_kind="mqtt", stale_after_sec=300)
    await engine._eval_rule(rt, now=2.0)
    assert rt.run_state == "firing"
    assert rt.consecutive_match_count == 1


async def test_an_edit_then_a_restart_before_the_first_tick_is_pending(
        db_engine, db_session, db_client, admin_key, make_rule, make_template, monkeypatch):
    """RV-04, rc.6 verification: the real PATCH aligns the streak's epoch in
    its own transaction, so a restart found no epoch difference and loaded the
    old condition's "firing" as current."""
    cache = await _cache(x=50)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="x > 10", persist_n=3)
    for _ in range(3):
        await engine._eval_rule(engine._rules[rid], now=0.0)
    assert engine._rules[rid].run_state == "firing"

    class _NoReload:
        async def reload_rules(self):
            return None
    monkeypatch.setattr("app.api.v1.rules.get_engine", lambda: _NoReload())
    r = await db_client.patch(f"/v1/rules/{rid}", json={"condition_expr": "x > 40"}, headers={"X-API-Key": admin_key})
    assert r.status_code == 200, r.text
    assert r.json()["run_state"] is None

    restarted = RuleEngine()                                   # a new process
    restarted._cache = cache
    await restarted.reload_rules()
    rt = restarted._rules[rid]
    assert rt.reconfigured
    await restarted._eval_rule(rt, now=1.0)
    assert (rt.consecutive_match_count, rt.run_state) == (1, "pending")
    for _ in range(2):
        await restarted._eval_rule(rt, now=2.0)
    assert rt.run_state == "firing"
    await fresh(db_session)
    rows = (await db_session.execute(select(RuleTransition).where(RuleTransition.rule_id == rid)
                                      .order_by(RuleTransition.id))).scalars().all()
    assert [(x.from_state, x.to_state, x.detail) for x in rows[-2:]] == [
        (None, "pending", "rule changed"), ("pending", "firing", None)]
