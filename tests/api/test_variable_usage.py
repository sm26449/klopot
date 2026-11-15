"""Variables: who reads them (used_by_*), value_state and the new filters;
rules: category and never_fired filters."""
from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from app.db.models import Input, InputKind, Rule, Template, Variable, VariableSource
from app.services.references import computed_vars, expression_vars, rule_vars


def test_expression_vars_include_helper_string_args():
    expr = 'not ac.commanded and ac.running and var_age("ac.running_state") < 120'
    assert expression_vars(expr) == {"ac.commanded", "ac.running", "ac.running_state"}
    assert expression_vars(None) == set()
    assert expression_vars("this is (not valid") == set()
    assert expression_vars("false") == set()                 # keyword literal, not a variable
    assert expression_vars("x.a > 1 and NULL is None") == {"x.a"}


def test_rule_and_computed_references():
    rule = Rule(name="r", template_type="t", condition_expr="a.x > 1", recovery_expr="a.y < 1",
                vars_extract=["a.z"])
    assert rule_vars(rule) == {"a.x", "a.y", "a.z"}
    comp = Variable(name="pv.net", source=VariableSource.computed, config={"formula": "pv.total - load.total"})
    assert computed_vars(comp) == {"pv.total", "load.total"}
    assert computed_vars(Variable(name="m", source=VariableSource.mqtt, config={"formula": "x"})) == set()


@pytest.fixture
async def world(db_session):
    from app.core.state_cache import VarSnapshot, get_state_cache, reset_state_cache_for_tests

    db_session.add(Input(id=7, name="broker", kind=InputKind.mqtt, config={}, enabled=True))
    db_session.add_all([
        Template(type="t_grid", severity="warning", title_template="t", category="Grid"),
        Template(type="t_none", severity="info", title_template="t"),
    ])
    db_session.add_all([
        Variable(id=1, name="grid.power", source=VariableSource.mqtt, input_id=7, config={}),
        Variable(id=2, name="grid.limit", source=VariableSource.constant, config={"value": 45}),
        Variable(id=3, name="pv.total", source=VariableSource.mqtt, input_id=7, config={}),
        Variable(id=4, name="pv.net", source=VariableSource.computed,
                 config={"formula": "pv.total - grid.power"}),
        Variable(id=5, name="orphan.thing", source=VariableSource.mqtt, config={}),
    ])
    db_session.add_all([
        Rule(id=1, name="over_export", template_type="t_grid", condition_expr="grid.power > grid.limit",
             persist_n=1, eval_interval_sec=30, vars_extract=[], enabled=True,
             last_fired_at=datetime(2026, 11, 1, tzinfo=UTC).replace(tzinfo=None)),
        Rule(id=2, name="pv_check", template_type="t_none", condition_expr='var_age("pv.net") > 60',
             persist_n=1, eval_interval_sec=30, vars_extract=[], enabled=True),
    ])
    await db_session.commit()

    reset_state_cache_for_tests()
    cache = get_state_cache()
    now = time.monotonic()
    cache._values["grid.power"] = VarSnapshot(value=10.0, ts=now, wall_ts=time.time())
    cache._values["pv.total"] = VarSnapshot(value=1.0, ts=now - 10_000, wall_ts=time.time() - 10_000)
    yield
    reset_state_cache_for_tests()


async def _vars(client, key, **q):
    r = await client.get("/v1/variables", params={"limit": 500, **q}, headers={"X-API-Key": key})
    assert r.status_code == 200, r.text
    return {v["name"]: v for v in r.json()["items"]}


async def test_usage_and_value_state(db_client, admin_key, world):
    v = await _vars(db_client, admin_key)
    assert v["grid.power"]["used_by_rules"] == ["over_export"]
    assert v["grid.power"]["used_by_variables"] == ["pv.net"]
    assert v["pv.net"]["used_by_rules"] == ["pv_check"]          # via var_age("pv.net")
    assert v["orphan.thing"]["used_by_rules"] == [] and v["orphan.thing"]["used_by_variables"] == []
    assert v["grid.power"]["value_state"] == "fresh"
    assert v["pv.total"]["value_state"] == "stale"
    assert v["orphan.thing"]["value_state"] == "missing"

    one = (await db_client.get("/v1/variables/grid.power", headers={"X-API-Key": admin_key})).json()
    assert one["used_by_variables"] == ["pv.net"]


@pytest.mark.parametrize(("query", "expected"), [
    ({"state": "missing"}, {"grid.limit", "pv.net", "orphan.thing"}),
    ({"state": "stale"}, {"pv.total"}),
    ({"used": "false"}, {"orphan.thing"}),
    ({"used": "true", "state": "fresh"}, {"grid.power"}),
    ({"input_id": 7}, {"grid.power", "pv.total"}),
])
async def test_variable_filters(db_client, admin_key, world, query, expected):
    assert set(await _vars(db_client, admin_key, **query)) == expected


@pytest.mark.parametrize(("query", "expected"), [
    ({"category": "grid"}, {"over_export"}),          # case-insensitive
    ({"category": "__none__"}, {"pv_check"}),
    ({"never_fired": "true"}, {"pv_check"}),
    ({"never_fired": "false"}, {"over_export"}),
])
async def test_rule_filters(db_client, admin_key, world, query, expected):
    r = await db_client.get("/v1/rules", params=query, headers={"X-API-Key": admin_key})
    assert r.status_code == 200, r.text
    assert {i["name"] for i in r.json()["items"]} == expected


async def test_bulk_enable_disable_rules(db_client, db_session, admin_key, world, monkeypatch):
    from sqlalchemy import select

    from app.api.v1 import rules as rules_api
    from app.db.models import AuditLog

    reloads = []

    class FakeEngine:
        async def reload_rules(self):
            reloads.append(1)

    monkeypatch.setattr(rules_api, "get_engine", lambda: FakeEngine())
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/bulk/enabled", json={"ids": [1, 2, 2, 99], "enabled": False}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": [1, 2], "unchanged": [], "not_found": [99]}
    assert reloads == [1]                                  # one reload for the batch

    r = await db_client.post("/v1/rules/bulk/enabled", json={"ids": [1], "enabled": False}, headers=h)
    assert r.json()["unchanged"] == [1] and reloads == [1]  # nothing changed → no reload

    audit = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "rule.update"))).scalars().all()
    assert sorted(a.resource_id for a in audit) == ["1", "2"]
    rows = (await db_client.get("/v1/rules", params={"enabled": "false"}, headers=h)).json()["items"]
    assert {i["name"] for i in rows} == {"over_export", "pv_check"}


async def test_bulk_requires_admin_scope(db_client, world):
    r = await db_client.post("/v1/rules/bulk/enabled", json={"ids": [1], "enabled": False})
    assert r.status_code == 401
