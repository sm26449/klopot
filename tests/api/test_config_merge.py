"""Selective export and item-by-item import (app/services/config_merge.py)."""
from __future__ import annotations

import pytest
import yaml
from sqlalchemy import select

from app.db.models import AuditLog, Channel, ChannelKind, Rule, Severity, Template, TemplateChannel, Variable, VariableSource


@pytest.fixture
async def world(db_session):
    db_session.add(Channel(id=1, name="tg", kind=ChannelKind.ui, config={}, enabled=True))
    db_session.add_all([
        Template(id=1, type="grid_over", severity=Severity.warning, title_template="Over {grid.power}", category="Grid"),
        Template(id=2, type="soc_low", severity=Severity.critical, title_template="SOC", category="Battery"),
    ])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=1, channel_id=1, severity_min=Severity.info, enabled=True))
    db_session.add_all([
        Variable(id=1, name="grid.power", source=VariableSource.constant, config={"value": 1}),
        Variable(id=2, name="grid.limit", source=VariableSource.constant, config={"value": 45}),
        Variable(id=3, name="battery.soc", source=VariableSource.constant, config={"value": 50}),
    ])
    db_session.add_all([
        Rule(id=1, name="over_export", template_type="grid_over", condition_expr="grid.power > grid.limit",
             persist_n=1, eval_interval_sec=30, vars_extract=[], enabled=True),
        Rule(id=2, name="soc_low_v1", template_type="soc_low", condition_expr="battery.soc < 10",
             persist_n=2, eval_interval_sec=30, vars_extract=[], enabled=True),
    ])
    await db_session.commit()


H = {}


async def _export(client, key, **q):
    r = await client.get("/v1/config/export", params=q, headers={"X-API-Key": key})
    assert r.status_code == 200, r.text
    return yaml.safe_load(r.text), r.headers["content-disposition"]


async def test_export_by_category_brings_routes_not_rules(db_client, admin_key, world):
    pack, disp = await _export(db_client, admin_key, sections="templates", category="grid")
    assert [t["type"] for t in pack["templates"]] == ["grid_over"]
    assert pack["routes"] == [{"template": "grid_over", "channel": "tg", "severity_min": "info",
                               "enabled": True, "channel_overrides": None}]
    assert "rules" not in pack and "variables" not in pack
    assert "klopot-templates-routes.yaml" in disp


async def test_export_rules_with_dependencies(db_client, admin_key, world):
    pack, _ = await _export(db_client, admin_key, sections="rules", names="over_export", with_dependencies="true")
    assert [r["name"] for r in pack["rules"]] == ["over_export"]
    assert [t["type"] for t in pack["templates"]] == ["grid_over"]
    assert sorted(v["name"] for v in pack["variables"]) == ["grid.limit", "grid.power"]
    assert len(pack["routes"]) == 1


async def test_export_unknown_section_and_full_export_unchanged(db_client, admin_key, world):
    r = await db_client.get("/v1/config/export", params={"sections": "rules,bogus"}, headers={"X-API-Key": admin_key})
    assert r.status_code == 422
    full, disp = await _export(db_client, admin_key)
    assert {"settings", "inputs", "templates", "channels", "variables", "rules", "routes", "schedules"} <= set(full)
    assert "alertd-config.yaml" in disp


def _pack(**sections):
    return yaml.safe_dump({"version": "1.0", **sections}, sort_keys=False)


async def _preview(client, key, text):
    r = await client.post("/v1/config/import/preview", content=text,
                          headers={"X-API-Key": key, "Content-Type": "application/yaml"})
    assert r.status_code == 200, r.text
    return r.json()


async def test_preview_classifies_items_and_shows_default_changes(db_client, admin_key, world):
    pack, _ = await _export(db_client, admin_key, sections="rules")
    soc = next(r for r in pack["rules"] if r["name"] == "soc_low_v1")
    soc["persist_n"] = 5
    over = next(r for r in pack["rules"] if r["name"] == "over_export")
    del over["sort_order"]                                    # identical: default == stored (100)
    pack["rules"].append({"name": "brand_new", "template_type": "soc_low", "condition_expr": "battery.soc < 5"})
    prev = await _preview(db_client, admin_key, yaml.safe_dump(pack))
    status = {i["key"]: i for i in prev["items"]}
    assert status["over_export"]["status"] == "identical"
    assert status["soc_low_v1"]["status"] == "differs"
    assert status["soc_low_v1"]["changes"] == [{"field": "persist_n", "current": 2, "incoming": 5}]
    assert status["brand_new"]["status"] == "new"
    assert prev["counts"] == {"new": 1, "identical": 1, "differs": 1}

    # An omitted field takes import's default, and the diff says so.
    text = _pack(templates=[{"type": "grid_over", "severity": "warning", "title_template": "Over {grid.power}",
                             "category": "Grid", "locale": "ro"}])
    item = (await _preview(db_client, admin_key, text))["items"][0]
    assert item["changes"] == [{"field": "locale", "current": "en", "incoming": "ro"}]


async def _apply(client, key, text, decisions=None, default="skip"):
    r = await client.post("/v1/config/import/apply", json={"yaml": text, "decisions": decisions or {},
                                                           "default_existing": default},
                          headers={"X-API-Key": key})
    assert r.status_code == 200, r.text
    return r.json()


async def test_apply_default_skip_keeps_existing(db_client, db_session, admin_key, world):
    text = _pack(rules=[{"name": "soc_low_v1", "template_type": "soc_low", "condition_expr": "battery.soc < 20"},
                        {"name": "fresh_rule", "template_type": "soc_low", "condition_expr": "battery.soc < 1"}])
    out = await _apply(db_client, admin_key, text)
    assert out["applied"] is True
    assert out["skipped"] == ["rules:soc_low_v1"] and out["created"] == ["rules:fresh_rule"]
    rows = {r.name: r for r in (await db_session.execute(select(Rule))).scalars()}
    await db_session.refresh(rows["soc_low_v1"])
    assert rows["soc_low_v1"].condition_expr == "battery.soc < 10"
    assert "fresh_rule" in rows


async def test_apply_overwrite_and_copy(db_client, db_session, admin_key, world):
    text = _pack(
        templates=[{"type": "grid_over", "severity": "critical", "title_template": "Incoming", "category": "Grid"}],
        routes=[{"template": "grid_over", "channel": "tg", "severity_min": "warning"}],
        rules=[{"name": "over_export", "template_type": "grid_over", "condition_expr": "grid.power > 50"},
               {"name": "soc_low_v1", "template_type": "soc_low", "condition_expr": "battery.soc < 15"}],
    )
    out = await _apply(db_client, admin_key, text, decisions={
        "templates:grid_over": "copy", "rules:over_export": "copy", "rules:soc_low_v1": "overwrite",
    })
    assert out["applied"] is True, out
    assert out["copied"] == {"templates:grid_over": "grid_over_copy", "rules:over_export": "over_export_copy"}
    db_session.expire_all()
    tmpl = {t.type: t for t in (await db_session.execute(select(Template))).scalars()}
    assert tmpl["grid_over"].title_template == "Over {grid.power}"       # original untouched
    assert tmpl["grid_over_copy"].title_template == "Incoming"
    rules = {r.name: r for r in (await db_session.execute(select(Rule))).scalars()}
    assert rules["over_export"].condition_expr == "grid.power > grid.limit"
    assert rules["over_export_copy"].template_type == "grid_over_copy"    # follows the copied template
    assert rules["soc_low_v1"].condition_expr == "battery.soc < 15"
    routes = (await db_session.execute(select(TemplateChannel))).scalars().all()
    by_tmpl = {r.template_id: r for r in routes}
    assert by_tmpl[tmpl["grid_over_copy"].id].severity_min == Severity.warning
    assert by_tmpl[tmpl["grid_over"].id].severity_min == Severity.info
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "config.import"))).scalars().all()
    assert audit and audit[-1].after["copied"]["templates:grid_over"] == "grid_over_copy"


async def test_skip_a_new_item_that_would_fail_validation(db_client, admin_key, world):
    text = _pack(routes=[{"template": "soc_low", "channel": "missing_channel"}],
                 rules=[{"name": "r_ok", "template_type": "soc_low", "condition_expr": "battery.soc < 3"}])
    prev = await _preview(db_client, admin_key, text)
    assert prev["ok"] is False and any("missing_channel" in e for e in prev["errors"])
    blocked = await _apply(db_client, admin_key, text)
    assert blocked["applied"] is False
    out = await _apply(db_client, admin_key, text, decisions={"routes:soc_low→missing_channel": "skip"})
    assert out["applied"] is True and out["created"] == ["rules:r_ok"]


async def test_import_reuses_category_spelling(db_client, db_session, admin_key, world):
    text = _pack(templates=[{"type": "pq_warn", "severity": "warning", "title_template": "PQ", "category": " grid "}])
    assert (await _apply(db_client, admin_key, text))["applied"] is True
    tmpl = (await db_session.execute(select(Template).where(Template.type == "pq_warn"))).scalar_one()
    assert tmpl.category == "Grid"


async def test_masked_url_echo_is_identical(db_client, db_session, admin_key, world):
    """A masked export shortens URLs (`http://host:5080/…`); import keeps the
    live URL for that echo, so the preview must call it identical (found on a
    production round-trip, 2026-11-14)."""
    from app.db.models import Input, InputKind
    db_session.add(Input(id=9, name="health", kind=InputKind.http_poll,
                         config={"url": "http://gateway:5080/api/health", "interval_sec": 120}, enabled=True))
    await db_session.commit()
    pack, _ = await _export(db_client, admin_key, sections="inputs", mask_secrets="true")
    assert pack["inputs"][0]["config"]["url"] != "http://gateway:5080/api/health"   # really masked
    prev = await _preview(db_client, admin_key, yaml.safe_dump(pack))
    assert [i["status"] for i in prev["items"]] == ["identical"]


async def test_a_config_import_adds_routes_to_existing_templates(db_client, db_session, admin_key, world):
    # A config file describes a configuration — its routes are meant (unlike a
    # pack's, which route everything to one channel): flagged, imported.
    text = _pack(routes=[{"template": "soc_low", "channel": "tg", "severity_min": "critical"}])
    prev = await _preview(db_client, admin_key, text)
    [item] = prev["items"]
    assert item["existing_template"] is True and item["default"] == "import"
    out = await _apply(db_client, admin_key, text)
    assert out["applied"] is True and out["created"] == ["routes:soc_low→tg"]


async def test_a_route_set_to_copy_falls_back_to_the_bulk_choice(db_client, admin_key, world):
    # Routes cannot be copied: "copy" on one takes the bulk choice — never a crash.
    text = _pack(routes=[{"template": "grid_over", "channel": "tg", "severity_min": "warning"}])
    out = await _apply(db_client, admin_key, text, decisions={"routes:grid_over→tg": "copy"})
    assert out["applied"] is True and out["skipped"] == ["routes:grid_over→tg"]
