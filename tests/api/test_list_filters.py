"""F3: new list filters — templates.search, rules.has_error/search,
variables.stale/search."""
from __future__ import annotations

import time

import pytest

from app.db.models import Rule, Severity, Template, Variable, VariableSource

pytestmark = pytest.mark.anyio


async def test_template_search(db_client, admin_key, db_session):
    db_session.add_all([
        Template(id=1, type="battery_low", severity=Severity.warning, title_template="Battery low"),
        Template(id=2, type="grid_outage", severity=Severity.critical, title_template="Grid down"),
    ])
    await db_session.commit()
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/templates", params={"search": "batter"}, headers=h)
    assert r.status_code == 200
    assert [t["type"] for t in r.json()["items"]] == ["battery_low"]


async def test_rules_has_error_and_search(db_client, admin_key, db_session):
    db_session.add_all([
        Rule(id=1, name="ok_rule", template_type="t", condition_expr="soc < 20",
             consecutive_eval_errors=0),
        Rule(id=2, name="broken_rule", template_type="t", condition_expr="bad expr",
             consecutive_eval_errors=4),
    ])
    await db_session.commit()
    h = {"X-API-Key": admin_key}

    r = await db_client.get("/v1/rules", params={"has_error": "true"}, headers=h)
    assert [x["name"] for x in r.json()["items"]] == ["broken_rule"]

    r = await db_client.get("/v1/rules", params={"has_error": "false"}, headers=h)
    assert [x["name"] for x in r.json()["items"]] == ["ok_rule"]

    r = await db_client.get("/v1/rules", params={"search": "soc"}, headers=h)
    assert [x["name"] for x in r.json()["items"]] == ["ok_rule"]


async def test_variables_search_and_stale(db_client, admin_key, db_session):
    db_session.add_all([
        Variable(id=1, name="batt_soc", source=VariableSource.mqtt, config={}),
        Variable(id=2, name="grid_freq", source=VariableSource.mqtt, config={}),
    ])
    await db_session.commit()

    from app.core.state_cache import VarSnapshot, get_state_cache, reset_state_cache_for_tests
    reset_state_cache_for_tests()
    cache = get_state_cache()
    now = time.monotonic()
    # batt_soc fresh, grid_freq stale (age ≫ default 300s window)
    cache._values["batt_soc"] = VarSnapshot(value=50.0, ts=now, wall_ts=time.time())
    cache._values["grid_freq"] = VarSnapshot(value=49.9, ts=now - 1000, wall_ts=time.time() - 1000)

    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/variables", params={"search": "batt"}, headers=h)
    assert [v["name"] for v in r.json()["items"]] == ["batt_soc"]

    r = await db_client.get("/v1/variables", params={"stale": "true"}, headers=h)
    assert [v["name"] for v in r.json()["items"]] == ["grid_freq"]

    r = await db_client.get("/v1/variables", params={"stale": "false"}, headers=h)
    names = [v["name"] for v in r.json()["items"]]
    assert "batt_soc" in names
    assert "grid_freq" not in names

    reset_state_cache_for_tests()
