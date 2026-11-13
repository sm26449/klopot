"""F3: GET /v1/settings (effective, read-only) + GET /v1/meta/kinds."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def test_settings_effective_readonly(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/settings", headers=h)
    assert r.status_code == 200, r.text
    items = {i["key"]: i for i in r.json()["items"]}
    assert items["tz"]["read_only"] is True
    assert items["tz"]["source"] in {"env", "default"}
    # database_url is present and read-only; any password component masked.
    assert items["database_url"]["read_only"] is True
    from app.api.v1.settings import _mask_db_url
    assert _mask_db_url("mysql+aiomysql://alertd:s3cret@mysql:3306/alertd") == \
        "mysql+aiomysql://alertd:***@mysql:3306/alertd"


async def test_settings_has_no_patch(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.patch("/v1/settings", json={"tz": "UTC"}, headers=h)
    assert r.status_code in (404, 405)


async def test_settings_requires_auth(db_client):
    r = await db_client.get("/v1/settings")
    assert r.status_code == 401


async def test_meta_kinds_shape(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/meta/kinds", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "channels" in body
    assert "inputs" in body
    assert "variables" in body
    assert "webhook_presets" in body

    # Telegram bot_token must be flagged secret, from the registry.
    tg_fields = {f["name"]: f for f in body["channels"]["telegram"]["fields"]}
    assert tg_fields["bot_token"]["secret"] is True
    assert tg_fields["bot_token"]["ref_field"] == "bot_token_ref"
    assert tg_fields["chat_id"]["secret"] is False

    # MQTT input password + username secret
    mqtt = {f["name"]: f for f in body["inputs"]["mqtt"]["fields"]}
    assert mqtt["password"]["secret"] is True
    assert mqtt["username"]["secret"] is True

    # Webhook presets include Discord et al.
    preset_ids = {p["id"] for p in body["webhook_presets"]}
    assert {"discord", "slack", "home_assistant", "generic"} <= preset_ids
