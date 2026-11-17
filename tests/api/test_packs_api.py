"""/v1/packs: catalog, preview, install; pack export and the plain import path."""
from __future__ import annotations

import pytest
import yaml
from sqlalchemy import select

from app.db.models import AuditLog, Channel, ChannelKind, Input, Rule, Template, TemplateChannel, Variable
from app.services import packs
from tests._db import fresh


@pytest.fixture
async def ui_channel(db_session):
    db_session.add(Channel(name="ui_default", kind=ChannelKind.ui, config={}, enabled=True))
    await db_session.commit()


def _h(key):
    return {"X-API-Key": key}


async def test_catalog_lists_and_serves_packs(db_client, admin_key):
    r = await db_client.get("/v1/packs", headers=_h(admin_key))
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["items"]}
    assert {"self-monitoring", "service-heartbeat", "sensor-threshold", "alertmanager"} <= ids
    one = (await db_client.get("/v1/packs/sensor-threshold", headers=_h(admin_key))).json()
    assert one["counts"]["rules"] == 2 and "pack:" in one["yaml"]
    assert {p["name"] for p in one["parameters"]} >= {"key", "topic", "threshold", "alert_channel"}
    assert (await db_client.get("/v1/packs/nope", headers=_h(admin_key))).status_code == 404


@pytest.mark.parametrize("pack_id", sorted(packs.catalog()))
async def test_every_catalog_pack_installs_on_an_empty_instance(db_client, admin_key, ui_channel, pack_id):
    """A broken catalog pack must fail the build, not a user's first install."""
    r = await db_client.post("/v1/packs/apply", json={"pack_id": pack_id}, headers=_h(admin_key))
    body = r.json()
    assert body["applied"] is True, body
    again = (await db_client.post("/v1/packs/preview", json={"pack_id": pack_id}, headers=_h(admin_key))).json()
    assert again["counts"]["new"] == 0 and again["counts"]["differs"] == 0, again  # reinstall = no-op


async def test_install_with_parameters_and_a_second_instance(db_client, admin_key, db_session, ui_channel):
    params = {"key": "fridge", "topic": "home/fridge/t", "threshold": 6, "broker_host": "broker.lan"}
    preview = (await db_client.post("/v1/packs/preview", json={"pack_id": "sensor-threshold", "params": params},
                                    headers=_h(admin_key))).json()
    assert preview["ok"] and preview["params"]["threshold"] == 6
    assert {(i["section"], i["key"]) for i in preview["items"]} >= {("rules", "fridge_above_threshold"), ("variables", "fridge_value")}
    assert (await db_client.post("/v1/packs/apply", json={"pack_id": "sensor-threshold", "params": params},
                                 headers=_h(admin_key))).json()["applied"]
    second = {**params, "key": "freezer", "topic": "home/freezer/t", "threshold": -10}
    assert (await db_client.post("/v1/packs/apply", json={"pack_id": "sensor-threshold", "params": second},
                                 headers=_h(admin_key))).json()["applied"]
    rules = {r.name: r.condition_expr for r in (await db_session.execute(select(Rule))).scalars()}
    assert rules["fridge_above_threshold"].endswith("fridge_value > 6")
    assert rules["freezer_above_threshold"].endswith("freezer_value > -10")
    inp = (await db_session.execute(select(Input).where(Input.name == "sensors_mqtt"))).scalar_one()
    assert inp.config == {"host": "broker.lan", "port": 1883}  # typed: port stays an int
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "pack.install"))).scalars().all()
    assert len(audit) == 2


async def test_fronius_installs_once_per_inverter_and_shares_the_collector_alerts(db_client, admin_key, db_session, ui_channel):
    """The collector-wide items are the same in every install: the second
    inverter finds them identical and adds only its own."""
    first = {"inverter_id": 1, "inverter_name": "Roof east"}
    assert (await db_client.post("/v1/packs/apply", json={"pack_id": "fronius-inverter", "params": first},
                                 headers=_h(admin_key))).json()["applied"]
    second = {"inverter_id": 2, "inverter_name": "Roof west"}
    preview = (await db_client.post("/v1/packs/preview", json={"pack_id": "fronius-inverter", "params": second},
                                    headers=_h(admin_key))).json()
    assert preview["counts"]["differs"] == 0, preview
    new = {(i["section"], i["key"]) for i in preview["items"] if i["status"] == "new"}
    assert ("rules", "fronius_inv2_fault") in new and ("variables", "fronius.inv2.v_max") in new
    assert not any("inv1" in key or key in {"fronius_collector_offline", "fronius.fleet"} for _, key in new)
    assert (await db_client.post("/v1/packs/apply", json={"pack_id": "fronius-inverter", "params": second},
                                 headers=_h(admin_key))).json()["applied"]
    rules = {r.name: r for r in (await db_session.execute(select(Rule))).scalars()}
    assert {"fronius_inv1_fault", "fronius_inv2_fault", "fronius_collector_offline"} <= set(rules)
    assert rules["fronius_inv2_throttled"].enabled is False   # opt-in: an export limit throttles on purpose


async def test_bad_parameters_are_reported_not_applied(db_client, admin_key, ui_channel):
    r = (await db_client.post("/v1/packs/apply", json={"pack_id": "sensor-threshold", "params": {"threshold": "warm"}},
                              headers=_h(admin_key))).json()
    assert r["applied"] is False and any("threshold" in e for e in r["errors"])
    r = await db_client.post("/v1/packs/preview", json={"pack_id": "x", "yaml": "a: 1"}, headers=_h(admin_key))
    assert r.status_code == 422  # exactly one source


async def test_route_to_a_missing_channel_is_a_validation_error(db_client, admin_key, ui_channel):
    r = (await db_client.post("/v1/packs/preview", json={"pack_id": "service-heartbeat", "params": {"alert_channel": "nowhere"}},
                              headers=_h(admin_key))).json()
    assert r["ok"] is False and any("nowhere" in e for e in r["errors"])


async def test_user_yaml_pack_inspect_and_install(db_client, admin_key, db_session, ui_channel):
    text = yaml.safe_dump({
        "pack": {"id": "mine", "name": "Mine", "parameters": [{"name": "level", "type": "number", "default": 3}]},
        "templates": [{"type": "mine_low", "severity": "warning", "title_template": "Low below ${level}"}],
        "routes": [{"template": "mine_low", "channel": "ui_default"}],
    })
    info = (await db_client.post("/v1/packs/inspect", json={"yaml": text}, headers=_h(admin_key))).json()
    assert info["ok"] and info["parameters"][0]["name"] == "level" and info["counts"] == {"templates": 1, "routes": 1}
    r = (await db_client.post("/v1/packs/apply", json={"yaml": text, "params": {"level": 5}}, headers=_h(admin_key))).json()
    assert r["applied"]
    t = (await db_session.execute(select(Template).where(Template.type == "mine_low"))).scalar_one()
    assert t.title_template == "Low below 5"


async def test_plain_import_accepts_a_header_but_refuses_parameters(db_client, admin_key, ui_channel):
    plain = yaml.safe_dump({"pack": {"id": "plain", "name": "P"}, "templates": [
        {"type": "p_t", "severity": "info", "title_template": "x"}]})
    r = (await db_client.post("/v1/config/import/preview", content=plain, headers={**_h(admin_key), "Content-Type": "application/yaml"})).json()
    assert r["ok"] and r["counts"]["new"] == 1
    with_params = packs.catalog_text("sensor-threshold")
    r = (await db_client.post("/v1/config/import/preview", content=with_params,
                              headers={**_h(admin_key), "Content-Type": "application/yaml"})).json()
    assert r["ok"] is False and "/v1/packs/apply" in r["errors"][0]


async def test_export_as_pack_closes_over_dependencies_and_reinstalls(db_client, admin_key, db_session, ui_channel):
    # Build a small world through a pack, then export one rule as a new pack.
    await db_client.post("/v1/packs/apply", json={"pack_id": "sensor-threshold", "params": {"key": "tank"}}, headers=_h(admin_key))
    r = await db_client.get("/v1/config/export", headers=_h(admin_key), params={
        "sections": "rules", "names": "tank_above_threshold", "with_dependencies": "true",
        "pack_id": "tank-alerts", "pack_name": "Tank alerts"})
    assert r.status_code == 200 and "tank-alerts.yaml" in r.headers["content-disposition"]
    doc = yaml.safe_load(r.text)
    assert doc["pack"] == {"id": "tank-alerts", "name": "Tank alerts", "version": "1.0.0"}
    assert list(doc)[:2] == ["pack", "version"]
    assert [x["name"] for x in doc["inputs"]] == ["sensors_mqtt"]           # variable → input
    assert [x["name"] for x in doc["variables"]] == ["tank_value"]           # rule → variable
    assert [x["type"] for x in doc["templates"]] == ["tank_too_high"]        # rule → template
    assert [x["name"] for x in doc["channels"]] == ["ui_default"]           # route → channel
    # The exported pack installs through /v1/packs (here: onto the same instance → all identical).
    again = (await db_client.post("/v1/packs/preview", json={"yaml": r.text}, headers=_h(admin_key))).json()
    assert again["ok"] and again["counts"]["new"] == 0 and again["counts"]["differs"] == 0, again


async def test_closure_follows_computed_formulas_inhibitors_and_gate_variables(db_client, admin_key, db_session, ui_channel):
    text = yaml.safe_dump({"pack": {"id": "deps", "name": "Deps"}, "variables": [
        {"name": "a", "source": "constant", "config": {"value": 1}},
        {"name": "b", "source": "computed", "config": {"formula": "a * 2"}},
        {"name": "g", "source": "constant", "config": {"value": 5}},
    ], "templates": [
        {"type": "t_main", "severity": "warning", "title_template": "x", "gate_variable": "g", "gate_min": 1},
        {"type": "t_inh", "severity": "info", "title_template": "y"},
    ], "rules": [
        {"name": "inhibitor", "template_type": "t_inh", "condition_expr": "a > 0"},
        {"name": "main", "template_type": "t_main", "condition_expr": "b > 1", "inhibited_by": ["inhibitor"]},
    ]})
    assert (await db_client.post("/v1/packs/apply", json={"yaml": text}, headers=_h(admin_key))).json()["applied"]
    doc = yaml.safe_load((await db_client.get("/v1/config/export", headers=_h(admin_key), params={
        "sections": "rules", "names": "main", "with_dependencies": "true"})).text)
    assert sorted(r["name"] for r in doc["rules"]) == ["inhibitor", "main"]
    assert sorted(v["name"] for v in doc["variables"]) == ["a", "b", "g"]
    assert sorted(t["type"] for t in doc["templates"]) == ["t_inh", "t_main"]
    assert (await db_session.execute(select(Variable).where(Variable.name == "b"))).scalar_one()


async def test_preview_reports_whether_each_secret_is_ready(db_client, admin_key, ui_channel, monkeypatch):
    """An `env` setting names a secret; the preview says whether Klopot may read
    it and whether it is set — never its value."""
    h = _h(admin_key)
    monkeypatch.delenv("KLOPOT_SECRET_ALERTMANAGER_TOKEN", raising=False)
    r = (await db_client.post("/v1/packs/preview", headers=h, json={"pack_id": "alertmanager"})).json()
    assert r["env"] == [{"param": "token_env", "name": "KLOPOT_SECRET_ALERTMANAGER_TOKEN", "allowed": True, "set": False}]
    monkeypatch.setenv("KLOPOT_SECRET_ALERTMANAGER_TOKEN", "s3cret-value")
    r = (await db_client.post("/v1/packs/preview", headers=h, json={"pack_id": "alertmanager"})).json()
    assert r["env"][0]["set"] is True and "s3cret-value" not in str(r)
    r = (await db_client.post("/v1/packs/preview", headers=h, json={"pack_id": "alertmanager", "params": {"token_env": "MY_TOKEN"}})).json()
    assert r["env"][0]["allowed"] is False  # not KLOPOT_SECRET_* and not allowlisted


# ── Routes to templates you already have (1.3.0-rc.2) ────────────────


@pytest.fixture
async def mbg_already_configured(db_session, ui_channel):
    """An instance where mbg_device exists and goes to the UI only, and a
    second channel the pack will be pointed at."""
    db_session.add_all([
        Channel(name="phone", kind=ChannelKind.ui, config={}, enabled=True),
        Template(type="mbg_device", severity="warning", title_template="{source}: {message}", min_repeat_min=15),
    ])
    await db_session.flush()
    tmpl = (await db_session.execute(select(Template).where(Template.type == "mbg_device"))).scalar_one()
    ui = (await db_session.execute(select(Channel).where(Channel.name == "ui_default"))).scalar_one()
    db_session.add(TemplateChannel(template_id=tmpl.id, channel_id=ui.id, enabled=True, severity_min="info"))
    await db_session.commit()


async def _routes(db_session, template_type):
    await fresh(db_session)
    rows = await db_session.execute(select(Channel.name).join(TemplateChannel, TemplateChannel.channel_id == Channel.id)
                                    .join(Template, Template.id == TemplateChannel.template_id)
                                    .where(Template.type == template_type))
    return set(rows.scalars())


MBG_TO_PHONE = {"pack_id": "multi-bus-gateway", "params": {"alert_channel": "phone"}}


async def test_a_pack_does_not_add_its_channel_to_a_template_you_already_route(
        db_client, admin_key, db_session, mbg_already_configured):
    preview = (await db_client.post("/v1/packs/preview", json=MBG_TO_PHONE, headers=_h(admin_key))).json()
    items = {(i["section"], i["key"]): i for i in preview["items"]}
    flagged = items[("routes", "mbg_device→phone")]
    assert flagged["status"] == "new" and flagged["existing_template"] is True and flagged["default"] == "skip"
    fresh_route = items[("routes", "mbg_device_ok→phone")]
    assert fresh_route["existing_template"] is False and fresh_route["default"] == "import"

    r = (await db_client.post("/v1/packs/apply", json=MBG_TO_PHONE, headers=_h(admin_key))).json()
    assert r["applied"] and "routes:mbg_device→phone" in r["skipped"]
    assert await _routes(db_session, "mbg_device") == {"ui_default"}, "the user's routing is untouched"
    assert await _routes(db_session, "mbg_device_ok") == {"phone"}, "new templates go where the pack says"


async def test_the_channel_is_added_to_an_existing_template_when_asked(
        db_client, admin_key, db_session, mbg_already_configured):
    body = {**MBG_TO_PHONE, "decisions": {"routes:mbg_device→phone": "import"}}
    r = (await db_client.post("/v1/packs/apply", json=body, headers=_h(admin_key))).json()
    assert r["applied"] and "routes:mbg_device→phone" in r["created"]
    assert await _routes(db_session, "mbg_device") == {"ui_default", "phone"}


async def test_import_never_overwrites_an_existing_item(db_client, admin_key, db_session, mbg_already_configured):
    # "import" adds new items only: on a template that differs it is a skip.
    body = {**MBG_TO_PHONE, "decisions": {"templates:mbg_device": "import"}}
    r = (await db_client.post("/v1/packs/apply", json=body, headers=_h(admin_key))).json()
    assert r["applied"] and "templates:mbg_device" in r["skipped"]
    await fresh(db_session)
    tmpl = (await db_session.execute(select(Template).where(Template.type == "mbg_device"))).scalar_one()
    assert tmpl.min_repeat_min == 15


async def test_default_existing_takes_only_existing_item_actions(db_client, admin_key, mbg_already_configured):
    # "import" is a decision for a new item, not a bulk choice for existing ones.
    body = {**MBG_TO_PHONE, "default_existing": "import"}
    assert (await db_client.post("/v1/packs/apply", json=body, headers=_h(admin_key))).status_code == 422
