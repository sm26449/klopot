"""API-level checks that literal secrets never leave the service
(audit 2026-11-07 C-1 / C-2) and that PATCH preserves them.

SQLite-backed via ``db_client`` + ``admin_key`` fixtures; the input
manager reload is patched out (no MQTT in tests).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.db.models import AuditLog
from app.secrets_registry import MASK

SECRET = "super-secret-broker-pw"
TOKEN = "123456:telegram-bot-token"


@pytest.fixture
def no_reload():
    """Inputs CRUD hot-reloads the input manager; stub it."""
    with patch("app.api.v1.inputs.get_manager") as gm:
        gm.return_value.reload = AsyncMock()
        yield gm


# ── Channels ──────────────────────────────────────────────────────


async def test_channel_read_masks_literal_token(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={
        "name": "tg_test", "kind": "telegram",
        "config": {"chat_id": "42", "bot_token": TOKEN},
    }, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["config"]["bot_token"] == MASK
    assert body["config"]["chat_id"] == "42"
    assert body["secret_fields_set"] == {"bot_token": "literal"}
    assert TOKEN not in r.text

    cid = body["id"]
    for path in ("/v1/channels", f"/v1/channels/{cid}"):
        r = await db_client.get(path, headers=h)
        assert r.status_code == 200
        assert TOKEN not in r.text


async def test_channel_read_reports_env_ref(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={
        "name": "tg_ref", "kind": "telegram",
        "config": {"chat_id": "42", "bot_token_ref": "TELEGRAM_BOT_TOKEN"},
    }, headers=h)
    assert r.status_code == 201
    assert r.json()["config"]["bot_token_ref"] == "TELEGRAM_BOT_TOKEN"
    assert r.json()["secret_fields_set"] == {"bot_token": "env:TELEGRAM_BOT_TOKEN"}


async def test_channel_patch_without_secret_keeps_it(db_client, admin_key, db_session):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={
        "name": "tg_patch", "kind": "telegram",
        "config": {"chat_id": "42", "bot_token": TOKEN},
    }, headers=h)
    cid = r.json()["id"]

    # Client edits chat_id using the masked read it received
    r = await db_client.patch(f"/v1/channels/{cid}", json={
        "config": {"chat_id": "43", "bot_token": MASK},
    }, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["config"] == {"chat_id": "43", "bot_token": MASK}

    from app.db.models import Channel
    row = (await db_session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
    await db_session.refresh(row)
    assert row.config["bot_token"] == TOKEN  # preserved in DB
    assert row.config["chat_id"] == "43"


# SQLite-only: under MySQL's REPEATABLE READ, db_session's snapshot doesn't see
# the request session's committed clear within the same transaction (V13 CI).
@pytest.mark.sqlite
async def test_channel_patch_can_replace_and_clear_secret(db_client, admin_key, db_session):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={
        "name": "tg_rot", "kind": "telegram",
        "config": {"chat_id": "42", "bot_token": TOKEN},
    }, headers=h)
    cid = r.json()["id"]
    from app.db.models import Channel

    r = await db_client.patch(f"/v1/channels/{cid}", json={
        "config": {"chat_id": "42", "bot_token": "new-token"},
    }, headers=h)
    assert r.status_code == 200
    row = (await db_session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
    await db_session.refresh(row)
    assert row.config["bot_token"] == "new-token"

    r = await db_client.patch(f"/v1/channels/{cid}", json={
        "config": {"chat_id": "42", "bot_token": ""},
    }, headers=h)
    assert r.status_code == 200
    assert r.json()["secret_fields_set"] == {}
    await db_session.refresh(row)
    assert "bot_token" not in row.config


# ── Inputs ────────────────────────────────────────────────────────


async def test_input_read_masks_mqtt_password_and_username(db_client, admin_key, no_reload):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/inputs", json={
        "name": "mqtt_test", "kind": "mqtt",
        "config": {"host": "broker", "port": 1883, "username": "alertd", "password": SECRET},
    }, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["config"]["password"] == MASK
    assert r.json()["config"]["username"] == MASK
    assert r.json()["config"]["host"] == "broker"
    assert SECRET not in r.text

    r = await db_client.get("/v1/inputs", headers=h)
    assert SECRET not in r.text


async def test_input_patch_preserves_secret_when_omitted(db_client, admin_key, no_reload, db_session):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/inputs", json={
        "name": "mqtt_patch", "kind": "mqtt",
        "config": {"host": "broker", "password": SECRET},
    }, headers=h)
    iid = r.json()["id"]
    r = await db_client.patch(f"/v1/inputs/{iid}", json={"config": {"host": "broker2"}}, headers=h)
    assert r.status_code == 200, r.text

    from app.db.models import Input
    row = (await db_session.execute(select(Input).where(Input.id == iid))).scalar_one()
    await db_session.refresh(row)
    assert row.config == {"host": "broker2", "password": SECRET}


# ── Audit log ─────────────────────────────────────────────────────


async def test_audit_snapshots_are_masked(db_client, admin_key, no_reload, db_session):
    h = {"X-API-Key": admin_key}
    await db_client.post("/v1/inputs", json={
        "name": "mqtt_audit", "kind": "mqtt",
        "config": {"host": "broker", "password": SECRET},
    }, headers=h)
    await db_client.post("/v1/channels", json={
        "name": "tg_audit", "kind": "telegram",
        "config": {"chat_id": "1", "bot_token": TOKEN},
    }, headers=h)

    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert rows, "expected audit rows"
    for row in rows:
        blob = str(row.before) + str(row.after)
        assert SECRET not in blob
        assert TOKEN not in blob
    inp = next(r for r in rows if r.resource_kind == "input")
    assert inp.after["config"]["password"] == MASK
    assert inp.after["config"]["host"] == "broker"


async def test_route_delete_masks_overrides_in_audit(db_client, admin_key, db_session):
    """Deleting a template→channel route must mask secret-bearing
    channel_overrides before they reach the audit snapshot — otherwise a
    read-scoped key could later read the plaintext from audit (A-05)."""
    h = {"X-API-Key": admin_key}
    route_secret = "route-only-auth-value"
    await db_client.post("/v1/templates", json={
        "type": "a05", "severity": "warning", "title_template": "{name}",
    }, headers=h)
    ch = (await db_client.post("/v1/channels", json={
        "name": "wh_a05", "kind": "webhook",
        "config": {"url": "https://example.test/hook"},
    }, headers=h)).json()
    # The route carries a per-route secret override (webhook auth_value).
    r = await db_client.put("/v1/templates/a05/channels", json=[{
        "channel_id": ch["id"], "severity_min": "info",
        "channel_overrides": {"auth_value": route_secret},
    }], headers=h)
    assert r.status_code == 200, r.text

    r = await db_client.delete(f"/v1/templates/a05/channels/{ch['id']}", headers=h)
    assert r.status_code == 204

    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "route.delete")
        )
    ).scalars().all()
    assert rows, "expected a route.delete audit row"
    for row in rows:
        assert route_secret not in (str(row.before) + str(row.after))
    assert rows[-1].before["channel_overrides"]["auth_value"] == MASK


# ── Scrub script ──────────────────────────────────────────────────


def test_scrub_snapshot_masks_and_is_idempotent():
    from scripts.scrub_audit_secrets import _scrub_snapshot

    snap = {"id": 1, "kind": "mqtt", "config": {"host": "b", "password": SECRET}}
    out, changed = _scrub_snapshot("input", snap)
    assert changed
    assert out["config"] == {"host": "b", "password": MASK}
    out2, changed2 = _scrub_snapshot("input", out)
    assert not changed2
    assert out2 == out
    assert _scrub_snapshot("input", None) == (None, False)
    assert _scrub_snapshot("input", {"kind": "mqtt"}) == ({"kind": "mqtt"}, False)
