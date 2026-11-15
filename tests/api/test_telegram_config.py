"""Actions are explicit, actor-scoped, and capabilities never appear in read APIs."""
from __future__ import annotations

import pytest

from app.core.telegram_service import TelegramService
from app.db.models import Channel
from tests.core.test_telegram_actions import callback, accept, rows, telegram_delivery as telegram_delivery


@pytest.mark.parametrize("config", [
    {"chat_id": "123", "inline_actions": True},
    {"chat_id": "@group", "inline_actions": True, "allowed_user_ids": [42]},
    {"chat_id": "123", "inline_actions": "true", "allowed_user_ids": [42]},
    {"chat_id": "123", "inline_actions": True, "allowed_user_ids": [True]},
    {"chat_id": "123", "inline_actions": True, "allowed_user_ids": [-42]},
    {"chat_id": "123", "inline_actions": True, "allowed_user_ids": "42"},
    {"chat_id": "123", "inline_actions": True, "allowed_user_ids": False, "any_chat_member": True},
    {"chat_id": "123", "admin_url": "https://user:secret@example.com/admin"},
    {"chat_id": "123", "admin_url": "https://example.com/admin?ack=secret"},
    {"chat_id": "123", "admin_url": "javascript:alert(1)"},
])
async def test_invalid_action_policy_is_rejected(db_client, admin_key, config):
    r = await db_client.post("/v1/channels", headers={"X-API-Key": admin_key}, json={
        "name": "telegram_test", "kind": "telegram", "config": config,
    })
    assert r.status_code == 422, r.text


async def test_legacy_channel_remains_opted_out(db_client, admin_key):
    r = await db_client.post("/v1/channels", headers={"X-API-Key": admin_key}, json={
        "name": "telegram_legacy", "kind": "telegram", "config": {"chat_id": "@group", "bot_token": "legacy-token"},
    })
    assert r.status_code == 201, r.text
    assert "inline_actions" not in r.json()["config"]
    assert "legacy-token" not in r.text


async def test_patch_cannot_enable_actions_without_actor_policy(db_client, admin_key, telegram_delivery):
    r = await db_client.patch(f"/v1/channels/{telegram_delivery['channel']}", headers={"X-API-Key": admin_key},
                             json={"config": {"chat_id": "123", "inline_actions": True}})
    assert r.status_code == 422, r.text
    assert (await rows(Channel))[0].config["allowed_user_ids"] == [42]


async def test_delivery_api_does_not_expose_callback_tokens(db_client, admin_key, telegram_delivery):
    r = await db_client.get(f"/v1/log/{telegram_delivery['log']}", headers={"X-API-Key": admin_key})
    assert r.status_code == 200
    assert "action_keyboard" not in r.text
    assert "callback_data" not in r.text
    assert "test-bot-token" not in r.text


async def test_shared_http_and_telegram_ack_preserve_first_actor(db_client, admin_key, telegram_delivery):
    case = telegram_delivery
    _, command_id = await accept(case, await callback(case))
    await TelegramService().process_command(command_id)
    r = await db_client.post(f"/v1/log/{case['log']}/ack", headers={"X-API-Key": admin_key})
    assert r.status_code == 200
    r = await db_client.get(f"/v1/log/{case['log']}", headers={"X-API-Key": admin_key})
    assert r.json()["acknowledged_by"] == "telegram:42"
