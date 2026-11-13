"""F16: a rule-scope snooze is matched by rule ID in gating, so the API
must reject a target that is not an existing rule id. Before the fix the
UI posted the rule *name*, which was stored verbatim and never matched any
rule, so the snooze silently did nothing.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.anyio


def _future() -> str:
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat()


async def _mk_rule(client, h, name="snz_rule") -> int:
    r = await client.post("/v1/rules", json={
        "name": name, "template_type": "batt_low",
        "condition_expr": "True", "persist_n": 1, "eval_interval_sec": 10,
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_rule_snooze_by_name_is_rejected(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_rule(db_client, h, name="named_rule")
    r = await db_client.post("/v1/snooze", json={
        "scope": "rule", "target": "named_rule", "until": _future(),
    }, headers=h)
    assert r.status_code == 422, r.text
    assert "rule id" in r.json()["detail"]


async def test_rule_snooze_unknown_id_is_rejected(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/snooze", json={
        "scope": "rule", "target": "999999", "until": _future(),
    }, headers=h)
    assert r.status_code == 422, r.text


async def test_rule_snooze_by_valid_id_succeeds(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    rid = await _mk_rule(db_client, h)
    r = await db_client.post("/v1/snooze", json={
        "scope": "rule", "target": str(rid), "until": _future(),
    }, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["target"] == str(rid)


async def test_type_snooze_target_is_not_constrained(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/snooze", json={
        "scope": "type", "target": "batt_low", "until": _future(),
    }, headers=h)
    assert r.status_code == 201, r.text
