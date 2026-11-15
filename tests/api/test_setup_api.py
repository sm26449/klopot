"""/v1/setup: the setup guide's steps come from the live configuration."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.channels.base import SendResult


def _h(key):
    return {"X-API-Key": key}


async def _status(client, key):
    r = await client.get("/v1/setup/status", headers=_h(key))
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {s["id"]: s["done"] for s in body["steps"]}


async def test_a_fresh_install_needs_everything(db_client, admin_key):
    body, done = await _status(db_client, admin_key)
    assert body["complete"] is False and body["dismissed"] is False and body["timezone"]
    assert done == {"channel": False, "channel_tested": False, "source": False, "rules": False, "first_alert": False}


async def test_steps_follow_the_configuration(db_client, admin_key):
    h = _h(admin_key)
    await db_client.post("/v1/channels", headers=h, json={"name": "ui_default", "kind": "ui", "config": {}})
    _, done = await _status(db_client, admin_key)
    assert done["channel"] is False  # the built-in UI channel does not count

    ch = (await db_client.post("/v1/channels", headers=h, json={
        "name": "ops_hook", "kind": "webhook", "config": {"url": "https://hooks.example.com/x"}})).json()
    _, done = await _status(db_client, admin_key)
    assert done["channel"] is True and done["channel_tested"] is False

    with patch("app.channels.webhook.WebhookChannel.send", AsyncMock(return_value=SendResult(ok=False, error="boom"))):
        assert (await db_client.post(f"/v1/channels/{ch['id']}/test", headers=h)).json()["ok"] is False
    _, done = await _status(db_client, admin_key)
    assert done["channel_tested"] is False  # a failed test does not count
    with patch("app.channels.webhook.WebhookChannel.send", AsyncMock(return_value=SendResult(ok=True))):
        assert (await db_client.post(f"/v1/channels/{ch['id']}/test", headers=h)).json()["ok"] is True
    _, done = await _status(db_client, admin_key)
    assert done["channel_tested"] is True

    # A fire-scoped key is a source; the script-alerts pack brings templates.
    await db_client.post("/v1/api_keys", headers=h, json={"name": "cron", "scopes": ["fire"]})
    assert (await db_client.post("/v1/packs/apply", headers=h, json={
        "pack_id": "script-alerts", "params": {"alert_channel": "ops_hook"}})).json()["applied"]
    _, done = await _status(db_client, admin_key)
    assert done["source"] is True and done["rules"] is True and done["first_alert"] is False

    with patch("app.channels.webhook.WebhookChannel.send", AsyncMock(return_value=SendResult(ok=True))):
        r = await db_client.post("/v1/fire", headers=h, json={"type": "script_warning", "context": {"title": "Backup late", "message": "26h"}})
    assert r.status_code == 202 and r.json()["title"] == "Backup late"
    body, done = await _status(db_client, admin_key)
    assert done["first_alert"] is True and body["complete"] is True


async def test_dismiss_and_reopen_are_audited(db_client, admin_key):
    h = _h(admin_key)
    assert (await db_client.post("/v1/setup/dismiss", headers=h)).json()["dismissed"] is True
    assert (await _status(db_client, admin_key))[0]["dismissed"] is True
    assert (await db_client.post("/v1/setup/reopen", headers=h)).json()["dismissed"] is False
    actions = [a["action"] for a in (await db_client.get("/v1/audit", headers=h, params={"resource_kind": "setup"})).json()["items"]]
    assert sorted(actions) == ["setup.dismiss", "setup.reopen"]


async def test_channel_test_message_names_klopot_and_fits_ui_and_api(db_client, admin_key):
    """The test notification a channel sends is what the operator reads on the
    phone: the product name, the channel, and no claim about where it came from."""
    from app.channels.base import Notification

    h = _h(admin_key)
    ch = (await db_client.post("/v1/channels", headers=h, json={
        "name": "ops_hook", "kind": "webhook", "config": {"url": "https://hooks.example.com/x"}})).json()
    sent: list[Notification] = []

    async def capture(self, notif, config, **kw):  # type: ignore[no-untyped-def]
        sent.append(notif)
        return SendResult(ok=True)

    with patch("app.channels.webhook.WebhookChannel.send", capture):
        assert (await db_client.post(f"/v1/channels/{ch['id']}/test", headers=h)).json()["ok"] is True
    n = sent[0]
    assert n.type == "channel_test" and n.title == "Test from Klopot (ops_hook)"
    assert "alertd" not in (n.title + n.message).lower() and "via the API" not in n.message


async def test_each_channel_test_is_a_new_message(db_client, admin_key):
    """Two tests must not share an idempotency key — a deduplicating gateway
    would replay the second (UI says "sent", nothing goes out)."""
    h = _h(admin_key)
    ch = (await db_client.post("/v1/channels", headers=h, json={
        "name": "gw", "kind": "webhook", "config": {"url": "https://hooks.example.com/x"}})).json()
    keys: list[str] = []

    async def capture(self, notif, config, *, idempotency_key=None):  # type: ignore[no-untyped-def]
        keys.append(idempotency_key)
        return SendResult(ok=True)

    with patch("app.channels.webhook.WebhookChannel.send", capture):
        for _ in range(2):
            await db_client.post(f"/v1/channels/{ch['id']}/test", headers=h)
    assert len(set(keys)) == 2 and all(k and k.startswith("test_gw_") and k.endswith(":gw") for k in keys)
