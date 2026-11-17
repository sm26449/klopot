"""Alertmanager / Grafana receiver (app/inputs/alertmanager.py +
app/services/alertmanager.py + POST /v1/inputs/{id}/webhook)."""
from __future__ import annotations

import copy
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.api.v1 import inputs as inputs_api
from app.db.models import Incident, Input, InputKind, NotificationLog, Severity, Template, TemplateChannel
from app.inputs.alertmanager import AlertmanagerInput, choose_type, parse_group, parse_time
from tests._db import fresh

FIRING = {
    "version": "4", "status": "firing", "receiver": "klopot", "groupKey": "{}:{alertname=\"DiskFull\"}",
    "externalURL": "http://am:9093", "truncatedAlerts": 0,
    "alerts": [
        {"status": "firing", "labels": {"alertname": "DiskFull", "instance": "nas:9100", "severity": "critical"},
         "annotations": {"summary": "Disk 95% full"}, "startsAt": "2026-11-14T10:00:00.123456789Z",
         "endsAt": "0001-01-01T00:00:00Z", "generatorURL": "http://prom/graph", "fingerprint": "f1"},
        {"status": "firing", "labels": {"alertname": "HighLoad", "instance": "nas:9100", "severity": "warning"},
         "annotations": {"summary": "load 12"}, "startsAt": "2026-11-14T10:01:00Z", "fingerprint": "f2"},
    ],
}
# Grafana unified alerting: same shape plus its own fields.
GRAFANA = {
    "receiver": "klopot", "status": "firing", "orgId": 1, "title": "[FIRING:1] CPU", "state": "alerting",
    "alerts": [{"status": "firing", "labels": {"alertname": "CPU", "grafana_folder": "infra"},
                "annotations": {"summary": "cpu high"}, "startsAt": "2026-11-14T10:00:00+02:00",
                "fingerprint": "g1", "valueString": "[ var='A' value=97 ]", "dashboardURL": "http://graf/d/x"}],
}


def test_parse_time_variants():
    assert parse_time("2026-11-14T10:00:00.123456789Z") == datetime(2026, 11, 14, 10, 0, 0, 123456)
    assert parse_time("2026-11-14T10:00:00+02:00") == datetime(2026, 11, 14, 8, 0, 0)
    assert parse_time("0001-01-01T00:00:00Z") is None
    assert parse_time("garbage") is None and parse_time(None) is None


def test_parse_group_bounds_and_errors():
    group = parse_group(FIRING)
    assert [a.fingerprint for a in group.alerts] == ["f1", "f2"]
    assert group.alerts[0].ends_at is None and group.common["receiver"] == "klopot"
    capped = parse_group({**FIRING, "truncatedAlerts": 3}, max_alerts=1)
    assert len(capped.alerts) == 1 and capped.truncated == 4
    bad = parse_group({"alerts": [{"status": "weird"}, "x", {"labels": {"a": "b"}}]})
    assert len(bad.alerts) == 1 and len(bad.errors) == 2
    assert bad.alerts[0].fingerprint, "a fingerprint is derived from labels when missing"
    assert parse_group({"nope": 1}).errors
    assert parse_group(GRAFANA).alerts[0].starts_at == datetime(2026, 11, 14, 8, 0)


def test_choose_type_order():
    a = parse_group(FIRING).alerts[0]
    cfg = {"default_type": "am_default", "type_by_severity": {"critical": "am_critical", "default": "am_info"}}
    # The label picks a template only among those label_types allows.
    assert choose_type(a, cfg, {"DiskFull", "am_critical"}) == "am_critical"
    assert choose_type(a, {**cfg, "label_types": ["DiskFull"]}, {"DiskFull", "am_critical"}) == "DiskFull"
    assert choose_type(a, {**cfg, "label_types": ["Disk*"]}, {"DiskFull", "am_critical"}) == "DiskFull"
    assert choose_type(a, {**cfg, "label_types": ["Net*"]}, {"DiskFull", "am_critical"}) == "am_critical"
    assert choose_type(a, cfg, {"am_critical"}) == "am_critical"
    assert choose_type(a, cfg, {"am_info"}) == "am_info"
    assert choose_type(a, cfg, set()) == "am_default"
    assert choose_type(a, {}, set()) == "alertmanager_alert"


@pytest.fixture
async def am_input(db_session, monkeypatch, make_channel):
    templates = [
        Template(type="am_critical", severity=Severity.critical, min_repeat_min=0,
                 title_template="{labels.alertname} on {labels.instance}: {annotations.summary}"),
        Template(type="am_default", severity=Severity.warning, min_repeat_min=0,
                 title_template="{labels.alertname}: {annotations.summary}"),
        Template(type="am_resolved", severity=Severity.info, min_repeat_min=0,
                 title_template="Resolved: {labels.alertname}"),
    ]
    # Routed: a resolution is announced only if its firing was.
    channel = make_channel(name="am_ui", rate_limit_per_min=1000)
    db_session.add_all([*templates, channel])
    await db_session.flush()
    db_session.add_all(TemplateChannel(template_id=t.id, channel_id=channel.id, enabled=True,
                                       severity_min=Severity.info) for t in templates)
    config = {"default_type": "am_default", "type_by_severity": {"critical": "am_critical"},
              "resolved_type": "am_resolved", "auth_token": "s3cret"}
    row = Input(id=5, name="prom", kind=InputKind.alertmanager, config=config, enabled=True)
    db_session.add(row)
    await db_session.commit()

    adapter = AlertmanagerInput(name="prom", config=config, on_value=lambda *a, **k: None)

    class FakeManager:
        def get_adapter(self, name):
            return adapter if name == "prom" else None

    monkeypatch.setattr(inputs_api, "get_manager", lambda: FakeManager())
    return row


async def _post(client, body, **headers):
    return await client.post("/v1/inputs/5/webhook", json=body, headers=headers)


async def _logs(db_session):
    await fresh(db_session)
    return (await db_session.execute(select(NotificationLog).order_by(NotificationLog.fired_at))).scalars().all()


async def test_auth_accepts_bearer_or_input_token(db_client, am_input):
    assert (await _post(db_client, FIRING)).status_code == 401
    assert (await _post(db_client, FIRING, Authorization="Bearer wrong")).status_code == 401
    assert (await _post(db_client, FIRING, Authorization="Bearer s3cret")).status_code == 202
    assert (await _post(db_client, FIRING, **{"X-Input-Token": "s3cret"})).status_code == 202


async def test_firing_repeat_resolved_round_trip(db_client, db_session, am_input):
    auth = {"Authorization": "Bearer s3cret"}
    r = (await _post(db_client, FIRING, **auth)).json()
    assert (r["alerts"], r["opened"], r["repeat"]) == (2, 2, 0)
    titles = [log.title for log in await _logs(db_session)]
    assert titles == ["DiskFull on nas:9100: Disk 95% full", "HighLoad: load 12"]

    r = (await _post(db_client, FIRING, **auth)).json()          # Alertmanager repeat_interval re-send
    assert (r["opened"], r["repeat"]) == (0, 2)
    assert len(await _logs(db_session)) == 2, "repeats notify nothing"

    resolved = copy.deepcopy(FIRING)
    resolved["status"] = "resolved"
    resolved["alerts"] = resolved["alerts"][:1]
    resolved["alerts"][0]["status"] = "resolved"
    r = (await _post(db_client, resolved, **auth)).json()
    assert r["resolved"] == 1
    logs = await _logs(db_session)
    assert logs[-1].title == "Resolved: DiskFull" and logs[-1].incident_event == "resolved"
    incidents = (await db_session.execute(select(Incident).order_by(Incident.source_key))).scalars().all()
    assert [(i.source_key, i.source_kind, i.resolved_at is not None) for i in incidents] == [
        ("am:5:f1", "alertmanager", True), ("am:5:f2", "alertmanager", False)]
    assert incidents[0].rule_name == "DiskFull"

    r = (await _post(db_client, resolved, **auth)).json()        # duplicate resolve
    assert r["resolved"] == 0 and r["ignored"] == 1


async def test_grafana_payload_and_truncation_notice(db_client, db_session, am_input):
    auth = {"X-Input-Token": "s3cret"}
    r = (await _post(db_client, {**GRAFANA, "truncatedAlerts": 2}, **auth)).json()
    assert (r["opened"], r["truncated"]) == (1, 2)
    logs = await _logs(db_session)
    assert logs[0].title == "CPU: cpu high"
    assert logs[-1].type == "alertmanager_truncated" and logs[-1].suppressed_reason.value == "unknown_type"


async def test_bad_bodies(db_client, db_session, am_input):
    auth = {"X-Input-Token": "s3cret"}
    r = await db_client.post("/v1/inputs/5/webhook", content=b"not json", headers=auth)
    assert r.status_code == 400
    assert (await _post(db_client, {"nope": 1}, **auth)).status_code == 400
    await fresh(db_session)
    assert (await db_session.execute(select(func.count()).select_from(Incident))).scalar_one() == 0


# ── Budgets: what one input may open (public-exposure review, Codex #3) ──


def _alerts(*fingerprints: str, status: str = "firing") -> dict:
    return {"version": "4", "status": status, "receiver": "klopot", "alerts": [
        {"status": status, "labels": {"alertname": f"A{fp}", "severity": "critical"},
         "annotations": {}, "fingerprint": fp} for fp in fingerprints]}


async def _configure(db_session, row, **config) -> None:
    row.config = {**row.config, **config}
    await db_session.commit()


async def _active(db_session) -> int:
    await fresh(db_session)
    return (await db_session.execute(
        select(func.count()).select_from(Incident).where(Incident.active_source_key.is_not(None)))).scalar_one()


async def test_new_episodes_a_minute_are_budgeted_and_reported_once(db_client, db_session, am_input):
    await _configure(db_session, am_input, max_new_episodes_per_min=2)
    auth = {"Authorization": "Bearer s3cret"}
    r = (await _post(db_client, _alerts("n1", "n2", "n3", "n4", "n5"), **auth)).json()
    assert (r["opened"], r["over_budget"]) == (2, 3)
    assert await _active(db_session) == 2
    notices = [log for log in await _logs(db_session) if log.type == "alertmanager_truncated"]
    assert len(notices) == 1, "one notice for the request, not one per alert"
    # Repeats of what is open are not budgeted.
    r = (await _post(db_client, _alerts("n1", "n2"), **auth)).json()
    assert (r["repeat"], r["over_budget"]) == (2, 0)


async def test_active_episodes_are_capped_and_resolving_makes_room(db_client, db_session, am_input):
    await _configure(db_session, am_input, max_active_episodes=2)
    auth = {"Authorization": "Bearer s3cret"}
    r = (await _post(db_client, _alerts("c1", "c2", "c3"), **auth)).json()
    assert (r["opened"], r["over_budget"]) == (2, 1)
    assert (await _post(db_client, _alerts("c1", status="resolved"), **auth)).json()["resolved"] == 1
    r = (await _post(db_client, _alerts("c3"), **auth)).json()        # Alertmanager re-sends it
    assert (r["opened"], r["over_budget"]) == (1, 0)
    assert await _active(db_session) == 2


async def test_an_out_of_range_stored_budget_is_clamped(db_client, db_session, am_input):
    from app.inputs import alertmanager as am

    assert am.limit({"max_alerts": 5000}, "max_alerts") == 1000
    assert am.limit({"max_alerts": "lots"}, "max_alerts") == 200
    assert am.limit({}, "max_active_episodes") == 500


@pytest.mark.parametrize(("config", "message"), [
    ({"max_alerts": 0}, "max_alerts must be a whole number from 1 to 1000"),
    ({"max_alerts": 1001}, "max_alerts must be a whole number from 1 to 1000"),
    ({"max_new_episodes_per_min": True}, "max_new_episodes_per_min must be a whole number"),
    ({"max_active_episodes": "9"}, "max_active_episodes must be a whole number"),
    ({"label_types": "am_*"}, "label_types must be a list"),
    ({"label_types": ["am_*", ""]}, "label_types must be a list"),
])
async def test_budgets_and_label_types_are_validated_on_save(db_client, admin_key, config, message):
    r = await db_client.post("/v1/inputs", headers={"X-API-Key": admin_key}, json={
        "name": "am_bad", "kind": "alertmanager",
        "config": {"default_type": "am_default", "auth_token": "a" * 40, **config}})
    assert r.status_code == 422
    assert message in r.text
