"""Operator workflows, lifecycle config validation and historical incident access."""
from __future__ import annotations

import bcrypt
import pytest

from app.db.models import ApiKey, AuditLog, Delivery, DeliveryState, Incident, NotificationLog, RuleState
from tests.core.test_incidents import evaluate, open_problem, read_all, scenario as scenario


async def test_ack_and_resolution_are_independent(db_client, admin_key, scenario):
    incident = await open_problem(scenario)
    headers = {"X-API-Key": admin_key}
    r = await db_client.post(f"/v1/incidents/{incident.id}/ack", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "active"
    assert r.json()["acknowledged_at"].endswith("Z")
    assert r.json()["resolved_at"] is None
    assert r.json()["opened_at"].endswith("Z")
    assert "opening_context" in r.json()
    first_ack = r.json()["acknowledged_at"]
    r = await db_client.post(f"/v1/incidents/{incident.id}/ack", headers=headers)
    assert r.json()["acknowledged_at"] == first_ack
    audits = [a for a in await read_all(AuditLog) if a.action == "incident.ack"]
    assert len(audits) == 1


async def test_manual_resolution_requires_reason_preserves_ack_and_resets_streak(db_client, admin_key, scenario):
    engine, rule_id = scenario
    incident = await open_problem(scenario)
    await evaluate(engine, rule_id, 90)  # one match accumulated under the old episode
    headers = {"X-API-Key": admin_key}
    url = f"/v1/incidents/{incident.id}/resolve"
    for reason in ("", "   "):
        assert (await db_client.post(url, json={"reason": reason}, headers=headers)).status_code == 422
    r = await db_client.post(url, json={"reason": "Device replaced"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "resolved"
    assert r.json()["acknowledged_at"] is None
    assert r.json()["resolution_reason"] == "manual: Device replaced"
    stamp = r.json()["resolved_at"]
    r = await db_client.post(url, json={"reason": "Repeated request"}, headers=headers)
    assert r.json()["resolved_at"] == stamp
    assert len(await read_all(NotificationLog)) == 1, "manual closure does not announce healthy telemetry"
    await engine.reload_rules()
    assert engine._rules[rule_id].consecutive_match_count == 0
    await evaluate(engine, rule_id, 90)
    assert len(await read_all(Incident)) == 1
    await evaluate(engine, rule_id, 90)
    assert len(await read_all(Incident)) == 2


async def test_log_ack_acknowledges_whole_episode_and_log_filter_links_it(db_client, admin_key, scenario):
    engine, rule_id = scenario
    incident = await open_problem(scenario)
    await evaluate(engine, rule_id, 91)
    await evaluate(engine, rule_id, 91)
    logs = await read_all(NotificationLog)
    assert len(logs) == 2
    headers = {"X-API-Key": admin_key}
    r = await db_client.post(f"/v1/log/{logs[0].id}/ack", headers=headers)
    assert r.status_code == 200, r.text
    assert (await read_all(Incident))[0].acknowledged_at is not None
    assert all(r.acknowledged_at is not None for r in await read_all(NotificationLog))
    r = await db_client.get("/v1/log", params={"incident_id": incident.id}, headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 2
    assert {row["incident_id"] for row in r.json()["items"]} == {incident.id}
    r = await db_client.get("/v1/log", params={"incident_id": "missing"}, headers=headers)
    assert r.json()["total"] == 0


async def test_incident_filters_and_read_scope(db_client, db_session, admin_key, scenario):
    incident = await open_problem(scenario)
    key = "incident_reader_key_123456"
    db_session.add(ApiKey(name="reader", key_prefix=key[:8], scopes=["read"], enabled=True,
                           key_hash=bcrypt.hashpw(key.encode(), bcrypt.gensalt(rounds=4)).decode()))
    await db_session.commit()
    h = {"X-API-Key": key}
    assert (await db_client.get(f"/v1/incidents/{incident.id}", headers=h)).status_code == 200
    assert (await db_client.get(f"/v1/incidents/{incident.id}")).status_code == 401
    assert (await db_client.post(f"/v1/incidents/{incident.id}/ack", headers=h)).status_code == 403
    assert (await db_client.post(f"/v1/incidents/{incident.id}/resolve", json={"reason": "done"}, headers=h)).status_code == 403
    for params, expected in (({"state": "active", "acknowledged": False}, 1), ({"state": "resolved"}, 0),
                             ({"rule_id": incident.rule_id}, 1), ({"search": "no_such_title"}, 0)):
        r = await db_client.get("/v1/incidents", params=params, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["total"] == expected
        assert all("opening_context" not in row for row in r.json()["items"])
    assert (await db_client.get("/v1/incidents/missing", headers=h)).status_code == 404


async def test_reconfig_closes_without_false_recovery_and_invalid_expr_is_atomic(db_client, admin_key, scenario):
    engine, rule_id = scenario
    await open_problem(scenario)
    h = {"X-API-Key": admin_key}
    url = f"/v1/rules/{rule_id}"
    r = await db_client.patch(url, json={"recovery_expr": "x +"}, headers=h)
    assert r.status_code == 422
    assert (await read_all(Incident))[0].state == "active"
    for body in ({"incident_enabled": None}, {"recovery_persist_n": None}, {"recovery_persist_n": 0}):
        assert (await db_client.patch(url, json=body, headers=h)).status_code == 422
    r = await db_client.patch(url, json={"recovery_expr": "x < 60"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["recovery_expr"] == "x < 60"
    [incident] = await read_all(Incident)
    assert incident.state == "resolved"
    assert incident.resolution_reason == "rule_reconfigured"
    assert len(await read_all(NotificationLog)) == 1
    assert all(d.state == DeliveryState.cancelled for d in await read_all(Delivery))
    assert (await read_all(RuleState))[0].recovery_match_count == 0


async def test_rule_deletion_preserves_open_incident_for_manual_review(db_client, admin_key, scenario):
    incident = await open_problem(scenario)
    h = {"X-API-Key": admin_key}
    r = await db_client.delete(f"/v1/rules/{incident.rule_id}", headers=h)
    assert r.status_code == 204, r.text
    r = await db_client.get(f"/v1/incidents/{incident.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["rule_id"] is None
    assert r.json()["rule_name"] == incident.rule_name
    assert r.json()["state"] == "active"
    r = await db_client.post(f"/v1/incidents/{incident.id}/resolve", json={"reason": "Rule retired"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "resolved"


async def test_rule_probe_and_test_fire_do_not_open_real_incidents(db_client, admin_key, scenario):
    _, rule_id = scenario
    h = {"X-API-Key": admin_key}
    assert (await db_client.post(f"/v1/rules/{rule_id}/eval-now", headers=h)).status_code == 200
    r = await db_client.post(f"/v1/rules/{rule_id}/test", json={"context": {"x": 90}}, headers=h)
    assert r.status_code == 200, r.text
    assert await read_all(Incident) == []
    [row] = await read_all(NotificationLog)
    assert row.is_test is True
    assert row.incident_id is None
