"""ADR-0005: parametric rules — one rule, one instance per value."""
from __future__ import annotations

import pytest
from sqlalchemy import select, update

from app.core.engine import RuleEngine
from app.core.parametric import RuleView, check_expressions, instances, normalize_for_each
from app.core.state_cache import StateCache
from app.db.models import Incident, NotificationLog, Rule, RuleInstance, RuleTransition
from tests._db import fresh

# ── The format ──────────────────────────────────────────────────────


def test_normalize_for_each():
    assert normalize_for_each(None) is None
    assert normalize_for_each({}) is None
    assert normalize_for_each({"n": ["f1", "f2"]}) == {"n": ["f1", "f2"]}
    assert instances(None) == [""]
    assert instances({"n": ["f1", "f2"]}) == ["f1", "f2"]


@pytest.mark.parametrize(("raw", "why"), [
    ({"n": ["a"], "m": ["b"]}, "one parameter"),
    ({"N": ["a"]}, "parameter name"),
    ({"n": []}, "non-empty"),
    ({"n": ["a b"]}, "a value must match"),
    ({"n": ["a", "a"]}, "listed twice"),
    ({"n": [str(i) for i in range(51)]}, "at most 50"),
    (["f1"], "one parameter"),
])
def test_normalize_for_each_refuses(raw, why):
    with pytest.raises(ValueError, match=why):
        normalize_for_each(raw)


def test_a_view_expands_and_writes_through(make_rule):
    r = make_rule(condition_expr='var_age("ov.{n}.state") < 600 AND ov.{n}.state == "Moderate"',
                  template_type="ov_active_{n}", vars_extract=["ov.{n}.limit_pct"], for_each={"n": ["f1", "f2"]})
    v = RuleView(r, "f2")
    assert v.condition_expr == 'var_age("ov.f2.state") < 600 AND ov.f2.state == "Moderate"'
    assert (v.template_type, v.vars_extract, v.binding, v.display_name) == (
        "ov_active_f2", ["ov.f2.limit_pct"], {"n": "f2"}, f"{r.name}[f2]")
    v.enabled = False
    assert r.enabled is False
    assert RuleView(r).condition_expr == r.condition_expr          # no instance: the rule itself


def test_every_instance_is_checked():
    from app.core.eval import ExpressionError, validate_expression
    check_expressions({"n": ["f1", "f2"]}, validate_expression, "ov.{n}.state > 1")
    with pytest.raises(ExpressionError, match=r"\[f1\]"):
        check_expressions({"n": ["f1"]}, validate_expression, "ov.{n}.state ++")


# ── The engine ─────────────────────────────────────────────────────


async def _cache(**values):
    cache = StateCache()
    for name, value in values.items():
        await cache.set(name.replace("__", "."), value, source_kind="mqtt", stale_after_sec=300)
    return cache


async def _setup(db_session, make_rule, make_template, cache, **kw):
    engine = RuleEngine()
    engine._cache = cache
    db_session.add_all([make_template(type="pt", min_repeat_min=0, title_template="hot {n}"),
                        make_rule(template_type="pt", for_each={"n": ["a", "b"]}, **kw)])
    await db_session.commit()
    rid = (await db_session.execute(select(Rule.id).where(Rule.template_type == "pt"))).scalar_one()
    await engine.reload_rules()
    return engine, rid


async def _tick(engine, rid, now=0.0):
    for inst in ("a", "b"):
        await engine._eval_rule(engine._rules[(rid, inst)], now=now)


async def test_each_instance_fires_on_its_own(db_engine, db_session, make_rule, make_template):
    cache = await _cache(x__a=50, x__b=1)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="x.{n} > 10")
    assert set(engine._rules) == {(rid, "a"), (rid, "b")}
    await _tick(engine, rid)
    await fresh(db_session)
    logs = (await db_session.execute(select(NotificationLog).where(NotificationLog.rule_id == rid))).scalars().all()
    assert [(log.title, log.vars_payload.get("n")) for log in logs] == [("hot a", "a")]
    states = {r.instance: r.run_state for r in (await db_session.execute(select(RuleInstance))).scalars()}
    assert states == {"a": "firing", "b": "inactive"}
    rule = (await db_session.execute(select(Rule).where(Rule.id == rid))).scalar_one()
    assert rule.run_state == "firing"                                   # the most urgent instance
    tr = (await db_session.execute(select(RuleTransition.instance, RuleTransition.to_state)
                                    .where(RuleTransition.rule_id == rid))).all()
    assert sorted(tr) == [("a", "firing"), ("b", "inactive")]
    # Both true: two notifications, kept apart by their parameter.
    await cache.set("x.b", 70, source_kind="mqtt", stale_after_sec=300)
    await _tick(engine, rid, now=1.0)
    await fresh(db_session)
    titles = sorted(log.title for log in (await db_session.execute(
        select(NotificationLog).where(NotificationLog.rule_id == rid))).scalars())
    assert titles.count("hot b") == 1                 # a re-fires too (persist 1, no throttle)


async def test_a_silent_instance_is_no_data_alone(db_engine, db_session, make_rule, make_template):
    cache = await _cache(x__a=1)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="x.{n} > 10")
    await _tick(engine, rid)
    await fresh(db_session)
    rows = {r.instance: r for r in (await db_session.execute(select(RuleInstance))).scalars()}
    assert (rows["a"].run_state, rows["b"].run_state) == ("inactive", "no_data")
    assert rows["b"].last_eval_error.startswith("missing input: x.b")
    rule = (await db_session.execute(select(Rule).where(Rule.id == rid))).scalar_one()
    assert rule.last_eval_error.startswith("[b] missing input: x.b")
    assert rule.consecutive_eval_errors == 0


async def test_an_incident_per_instance(db_engine, db_session, make_rule, make_template):
    cache = await _cache(x__a=50, x__b=50)
    engine, rid = await _setup(db_session, make_rule, make_template, cache,
                               condition_expr="x.{n} > 10", incident_enabled=True)
    await _tick(engine, rid)
    await fresh(db_session)
    open_ = {i.active_source_key: i for i in (await db_session.execute(
        select(Incident).where(Incident.resolved_at.is_(None)))).scalars()}
    assert set(open_) == {f"rule:{rid}:a", f"rule:{rid}:b"}
    assert all(i.active_rule_id is None and i.rule_id == rid for i in open_.values())
    assert {i.rule_name.split("[")[1] for i in open_.values()} == {"a]", "b]"}
    await cache.set("x.a", 1, source_kind="mqtt", stale_after_sec=300)
    await _tick(engine, rid, now=1.0)
    await fresh(db_session)
    still = (await db_session.execute(select(Incident.active_source_key).where(Incident.resolved_at.is_(None)))).scalars().all()
    assert still == [f"rule:{rid}:b"]
    assert engine._rules[(rid, "b")].run_state == "firing"
    assert engine._rules[(rid, "a")].run_state == "inactive"


async def test_changing_the_values_closes_the_dropped_instances(db_engine, db_session, db_client, admin_key,
                                                                make_rule, make_template, monkeypatch):
    cache = await _cache(x__a=50, x__b=50)
    engine, rid = await _setup(db_session, make_rule, make_template, cache,
                               condition_expr="x.{n} > 10", incident_enabled=True)
    await _tick(engine, rid)

    class _NoReload:
        async def reload_rules(self):
            return None
    monkeypatch.setattr("app.api.v1.rules.get_engine", lambda: _NoReload())
    r = await db_client.patch(f"/v1/rules/{rid}", json={"for_each": {"n": ["a"]}}, headers={"X-API-Key": admin_key})
    assert r.status_code == 200, r.text
    await fresh(db_session)
    assert (await db_session.execute(select(Incident).where(Incident.resolved_at.is_(None)))).scalars().all() == []
    assert (await db_session.execute(select(RuleInstance))).scalars().all() == []
    await engine.reload_rules()
    assert set(engine._rules) == {(rid, "a")}


async def test_an_inhibitor_is_active_if_any_instance_is(db_engine, db_session, make_rule, make_template):
    cache = await _cache(x__a=1, x__b=50, y=1)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="x.{n} > 10")
    root = (await db_session.execute(select(Rule).where(Rule.id == rid))).scalar_one()
    db_session.add(make_rule(name="leaf", template_type="pt", condition_expr="y == 1", inhibited_by=[root.name]))
    await db_session.commit()
    await engine.reload_rules()
    await _tick(engine, rid)
    leaf = next(rt for rt in engine._rules.values() if rt.rule.name == "leaf")
    assert engine._active_inhibitor(leaf, 0.0) == root.name


async def test_history_needs_are_expanded(db_engine, db_session, make_rule, make_template):
    from app.core.history import get_history_store
    from app.core.state_cache import get_state_cache
    engine, _ = await _setup(db_session, make_rule, make_template, get_state_cache(),
                             condition_expr='avg_over("x.{n}", "5m") > 10')
    assert get_history_store().tracked() == {"x.a": 300, "x.b": 300}
    assert engine


async def test_a_cold_start_restores_each_instance(db_engine, db_session, make_rule, make_template):
    cache = await _cache(x__a=50, x__b=1)
    engine, rid = await _setup(db_session, make_rule, make_template, cache, condition_expr="x.{n} > 10", persist_n=3)
    await _tick(engine, rid)
    restarted = RuleEngine()
    restarted._cache = cache
    await restarted.reload_rules()
    a, b = restarted._rules[(rid, "a")], restarted._rules[(rid, "b")]
    assert (a.consecutive_match_count, a.run_state, b.run_state) == (1, "pending", "inactive")


# ── The API ────────────────────────────────────────────────────────


async def test_api_create_validate_instances_eval_now(db_client, admin_key, db_session, make_template, monkeypatch):
    h = {"X-API-Key": admin_key}

    class _NoReload:
        async def reload_rules(self):
            return None
    monkeypatch.setattr("app.api.v1.rules.get_engine", lambda: _NoReload())
    db_session.add(make_template(type="pt"))
    await db_session.commit()
    bad = await db_client.post("/v1/rules", headers=h, json={
        "name": "pbad", "template_type": "pt", "condition_expr": "x.{n} >", "for_each": {"n": ["a"]}})
    assert bad.status_code == 422
    assert "[a]" in bad.text
    bad_values = await db_client.post("/v1/rules", headers=h, json={
        "name": "pbad2", "template_type": "pt", "condition_expr": "x > 1", "for_each": {"n": ["a", "a"]}})
    assert bad_values.status_code == 422
    r = await db_client.post("/v1/rules", headers=h, json={
        "name": "pok", "template_type": "pt", "condition_expr": "x.{n} > 10", "for_each": {"n": ["a", "b"]}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["for_each"] == {"n": ["a", "b"]}
    inst = (await db_client.get(f"/v1/rules/{rid}/instances", headers=h)).json()
    assert [i["instance"] for i in inst] == ["a", "b"]
    assert (await db_client.post(f"/v1/rules/{rid}/eval-now?instance=zz", headers=h)).status_code == 404
    from app.core.state_cache import get_state_cache, reset_state_cache_for_tests
    reset_state_cache_for_tests()
    await get_state_cache().set("x.b", 50, source_kind="mqtt", stale_after_sec=300)
    ev = (await db_client.post(f"/v1/rules/{rid}/eval-now?instance=b", headers=h)).json()
    assert (ev["matched"], ev["instance"]) == (True, "b")
    v = (await db_client.post("/v1/rules/validate", headers=h, json={
        "condition_expr": "x.{n} > 10", "for_each": {"n": ["a", "b"]}, "instance": "b"})).json()
    assert (v["ok"], v["result"]) == (True, True)
    assert [x["name"] for x in v["referenced_vars"]] == ["x.b"]
    plain = (await db_client.get(f"/v1/rules/{rid}/transitions?instance=a", headers=h))
    assert plain.status_code == 200
    reset_state_cache_for_tests()


async def test_export_and_import_carry_for_each(db_session, make_rule, make_template):
    from app.services.config_io import _export_rules
    db_session.add_all([make_template(type="pt"), make_rule(name="pe", template_type="pt",
                                                            condition_expr="x.{n} > 1", for_each={"n": ["a"]})])
    await db_session.commit()
    rows = {r["name"]: r for r in await _export_rules(db_session)}
    assert rows["pe"]["for_each"] == {"n": ["a"]}
    await db_session.execute(update(Rule).where(Rule.name == "pe").values(for_each=None))
    await db_session.commit()
    rows = {r["name"]: r for r in await _export_rules(db_session)}
    assert "for_each" not in rows["pe"]


def test_variable_usage_sees_every_instance(make_rule):
    from app.services.references import rule_vars
    r = make_rule(condition_expr='var_age("ov.{n}.state") < 600', vars_extract=["ov.{n}.limit"],
                  for_each={"n": ["f1", "f2"]})
    assert rule_vars(r) == {"ov.f1.state", "ov.f2.state", "ov.f1.limit", "ov.f2.limit"}


async def test_config_import_takes_and_checks_for_each(db_client, admin_key, db_session, make_template):
    import json
    h = {"X-API-Key": admin_key, "content-type": "application/yaml"}
    db_session.add(make_template(type="pt"))
    await db_session.commit()
    good = {"version": "1.0", "rules": [{"name": "pimp", "template_type": "pt", "condition_expr": "x.{n} > 1",
                                         "for_each": {"n": ["a", "b"]}}]}
    resp = await db_client.post("/v1/config/import?apply=true", headers=h, content=json.dumps(good))
    assert resp.status_code == 200, resp.text
    await fresh(db_session)
    assert (await db_session.execute(select(Rule.for_each).where(Rule.name == "pimp"))).scalar_one() == {"n": ["a", "b"]}
    bad = {"version": "1.0", "rules": [{"name": "pimp2", "template_type": "pt", "condition_expr": "x.{n} >",
                                        "for_each": {"n": ["a"]}}]}
    resp = await db_client.post("/v1/config/import?apply=true", headers=h, content=json.dumps(bad))
    body = resp.json()
    assert body["applied"] is False
    assert any("[a]" in e for e in body["errors"])
