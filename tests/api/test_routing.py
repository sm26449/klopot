"""F3: template → channel routing, channel usage, in-use delete guard."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def _mk_template(client, h, type="batt_low"):
    r = await client.post("/v1/templates", json={
        "type": type, "severity": "warning", "title_template": "{name}",
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def _mk_channel(client, h, name):
    r = await client.post("/v1/channels", json={"name": name, "kind": "ui"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def test_put_and_get_routes_by_name_and_id(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    ch1 = await _mk_channel(db_client, h, "ui_a")
    ch2 = await _mk_channel(db_client, h, "ui_b")

    r = await db_client.put("/v1/templates/batt_low/channels", json=[
        {"channel_name": "ui_a", "severity_min": "warning"},
        {"channel_id": ch2["id"], "enabled": False},
    ], headers=h)
    assert r.status_code == 200, r.text
    routes = {x["channel_name"]: x for x in r.json()}
    assert routes["ui_a"]["severity_min"] == "warning"
    assert routes["ui_b"]["enabled"] is False
    assert routes["ui_a"]["channel_id"] == ch1["id"]

    r = await db_client.get("/v1/templates/batt_low/channels", headers=h)
    assert r.status_code == 200
    assert {x["channel_name"] for x in r.json()} == {"ui_a", "ui_b"}


async def test_put_is_atomic_replace(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    await _mk_channel(db_client, h, "ui_a")
    await _mk_channel(db_client, h, "ui_b")
    await db_client.put("/v1/templates/batt_low/channels",
                        json=[{"channel_name": "ui_a"}, {"channel_name": "ui_b"}], headers=h)
    # Replace with just ui_b → ui_a is unlinked
    r = await db_client.put("/v1/templates/batt_low/channels",
                            json=[{"channel_name": "ui_b"}], headers=h)
    assert [x["channel_name"] for x in r.json()] == ["ui_b"]


async def test_put_unknown_channel_422(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    r = await db_client.put("/v1/templates/batt_low/channels",
                            json=[{"channel_name": "does_not_exist"}], headers=h)
    assert r.status_code == 422


async def test_put_duplicate_channel_422(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    await _mk_channel(db_client, h, "ui_a")
    r = await db_client.put("/v1/templates/batt_low/channels",
                            json=[{"channel_name": "ui_a"}, {"channel_name": "ui_a"}], headers=h)
    assert r.status_code == 422


async def test_route_requires_identifier_422(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    r = await db_client.put("/v1/templates/batt_low/channels",
                            json=[{"severity_min": "info"}], headers=h)
    assert r.status_code == 422


async def test_delete_single_route(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    ch = await _mk_channel(db_client, h, "ui_a")
    await db_client.put("/v1/templates/batt_low/channels",
                        json=[{"channel_name": "ui_a"}], headers=h)
    r = await db_client.delete(f"/v1/templates/batt_low/channels/{ch['id']}", headers=h)
    assert r.status_code == 204
    r = await db_client.get("/v1/templates/batt_low/channels", headers=h)
    assert r.json() == []
    # Deleting a non-existent route → 404
    r = await db_client.delete(f"/v1/templates/batt_low/channels/{ch['id']}", headers=h)
    assert r.status_code == 404


async def test_channel_usage_and_in_use_delete_409(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    ch = await _mk_channel(db_client, h, "ui_a")
    await db_client.put("/v1/templates/batt_low/channels",
                        json=[{"channel_name": "ui_a"}], headers=h)

    r = await db_client.get(f"/v1/channels/{ch['id']}/usage", headers=h)
    assert r.status_code == 200
    assert [t["type"] for t in r.json()["templates"]] == ["batt_low"]

    r = await db_client.delete(f"/v1/channels/{ch['id']}", headers=h)
    assert r.status_code == 409
    detail = r.json()["detail"] if "detail" in r.json() else r.json()
    assert "batt_low" in str(detail)

    # Unlink then delete succeeds
    await db_client.delete(f"/v1/templates/batt_low/channels/{ch['id']}", headers=h)
    r = await db_client.delete(f"/v1/channels/{ch['id']}", headers=h)
    assert r.status_code == 204


async def test_routing_requires_admin_for_write(db_client, admin_key, db_session):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    await _mk_channel(db_client, h, "ui_a")
    # Seed a read-only key
    import bcrypt

    from app.db.models import ApiKey
    pt = "alertd_readonly_key_zzzzzzzz"
    db_session.add(ApiKey(
        id=77, name="ro", key_hash=bcrypt.hashpw(pt.encode(), bcrypt.gensalt(rounds=4)).decode(),
        key_prefix=pt[:8], scopes=["read"], enabled=True,
    ))
    await db_session.commit()
    r = await db_client.put("/v1/templates/batt_low/channels",
                            json=[{"channel_name": "ui_a"}], headers={"X-API-Key": pt})
    assert r.status_code == 403
    # ...but read is allowed
    r = await db_client.get("/v1/templates/batt_low/channels", headers={"X-API-Key": pt})
    assert r.status_code == 200


# ── F02: route override secrets must not leak ─────────────────────

_ROUTE_SECRET = "ROUTE_SECRET_XYZ"


async def _mk_webhook(client, h, name):
    r = await client.post("/v1/channels", json={
        "name": name, "kind": "webhook", "config": {"url": "https://x.test/h"},
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def test_route_override_secret_is_masked_on_read(db_client, admin_key):
    from app.secrets_registry import MASK
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h, "f02t")
    await _mk_webhook(db_client, h, "f02wh")
    r = await db_client.put("/v1/templates/f02t/channels", json=[
        {"channel_name": "f02wh", "severity_min": "info",
         "channel_overrides": {"auth_value": _ROUTE_SECRET}},
    ], headers=h)
    assert r.status_code == 200, r.text
    g = await db_client.get("/v1/templates/f02t/channels", headers=h)
    assert _ROUTE_SECRET not in g.text   # literal never leaves
    assert MASK in g.text                # it's redacted


async def test_route_override_secret_masked_in_export(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h, "f02e")
    await _mk_webhook(db_client, h, "f02ewh")
    await db_client.put("/v1/templates/f02e/channels", json=[
        {"channel_name": "f02ewh", "severity_min": "info",
         "channel_overrides": {"auth_value": _ROUTE_SECRET}},
    ], headers=h)
    exp = await db_client.get("/v1/config/export", params={"mask_secrets": "true"}, headers=h)
    assert exp.status_code == 200
    assert _ROUTE_SECRET not in exp.text   # masked export must not leak it


async def test_route_override_mask_echo_preserves_secret(db_client, admin_key):
    from app.secrets_registry import MASK
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h, "f02p")
    await _mk_webhook(db_client, h, "f02pwh")
    await db_client.put("/v1/templates/f02p/channels", json=[
        {"channel_name": "f02pwh", "severity_min": "info",
         "channel_overrides": {"auth_value": _ROUTE_SECRET}},
    ], headers=h)
    # Client read the masked routes and echoes the MASK back on save.
    await db_client.put("/v1/templates/f02p/channels", json=[
        {"channel_name": "f02pwh", "severity_min": "info",
         "channel_overrides": {"auth_value": MASK}},
    ], headers=h)
    # The real secret must survive (unmasked export still has it).
    exp = await db_client.get("/v1/config/export", headers=h)
    assert _ROUTE_SECRET in exp.text
