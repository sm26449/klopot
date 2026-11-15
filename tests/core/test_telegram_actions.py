"""Trusted Telegram callbacks: durable acceptance, actor policy and exactly-once local effects."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.channels.base import SendResult
from app.channels.telegram_config import bot_key
from app.core import channel_actions, outbox
from app.core.delivery_worker import DeliveryWorker
from app.core.notification_actions import acknowledge_notification
from app.core.retention import RetentionService
from app.core.telegram_service import TelegramService
from app.db import get_session_factory
from app.db.models import (
    AuditLog, Channel, ChannelActionCommand, ChannelActionToken, ChannelEvent,
    ChannelProviderCommand, ChannelProviderMessage, Delivery, DeliveryState,
    DeliveryStatus, Incident, NotificationLog, Severity, Snooze, TelegramBotState,
)
from app.utils.telegram_api import TelegramAPIError
from app.utils.time import utc_now


@pytest.fixture
async def telegram_delivery(db_session, make_channel):
    cfg = {"bot_token": "test-bot-token", "chat_id": "123", "inline_actions": True,
           "allowed_user_ids": [42], "actions_locale": "ro"}
    channel = make_channel(name="telegram_actions", kind="telegram", config=cfg)
    # ORM enum values are normally supplied by the public DTO.
    from app.db.models import ChannelKind

    channel.kind = ChannelKind.telegram
    log = NotificationLog(id="ntf_telegram", type="alarm", title="Alarm", severity=Severity.critical,
                          delivery_status=DeliveryStatus.pending)
    db_session.add_all([channel, log])
    await db_session.flush()
    delivery = outbox.enqueue(db_session, log.id, [channel.name], effective_by_name={channel.name: cfg},
                              effective_kind_by_name={channel.name: "telegram"}, background_only=True)[0]
    # MySQL DATETIME rounds fractional seconds; use an unambiguously due time.
    delivery.next_attempt_at = utc_now() - timedelta(seconds=2)
    await db_session.commit()
    service = TelegramService()
    await service.ensure_state(bot_key(cfg["bot_token"]))
    return {"delivery": delivery.id, "channel": channel.id, "log": log.id, "config": cfg,
            "key": bot_key(cfg["bot_token"]), "service": service}


async def rows(model):
    async with get_session_factory()() as session:
        return list((await session.execute(select(model))).scalars())


async def callback(case, action="ack", *, update_id=100, user=42, chat=123, message_id=7):
    token = next(t for t in await rows(ChannelActionToken) if t.delivery_id == case["delivery"] and t.action == action)
    return {"update_id": update_id, "callback_query": {"id": f"query_{update_id}", "from": {"id": user},
            "message": {"chat": {"id": chat}, "message_id": message_id}, "data": "k:" + token.id}}


async def accept(case, payload):
    async with get_session_factory()() as session:
        result = await channel_actions.ingest_update(session, case["key"], payload)
        await session.commit()
        return result


async def make_command_due(command_id):
    async with get_session_factory()() as session:
        command = await session.get(ChannelActionCommand, command_id)
        command.next_attempt_at = utc_now() - timedelta(seconds=2)
        await session.commit()


async def test_tokens_exist_before_transport_and_are_not_ids_or_actions(telegram_delivery):
    [delivery] = await rows(Delivery)
    tokens = await rows(ChannelActionToken)
    assert len(tokens) == 3
    assert len({t.id for t in tokens}) == 3
    assert all(t.expires_at > utc_now() + timedelta(hours=23) for t in tokens)
    buttons = [b for row in delivery.action_keyboard["inline_keyboard"] for b in row]
    assert all(len(b["callback_data"].encode()) <= 64 for b in buttons)
    assert all("ntf_" not in b["callback_data"] and "snooze" not in b["callback_data"] for b in buttons)
    assert await rows(ChannelProviderMessage) == []


async def test_receipt_command_cursor_survive_restart_and_ack_is_once(telegram_delivery):
    case = telegram_delivery
    payload = await callback(case)
    result, command_id = await accept(case, payload)
    assert result == "accepted"
    assert (await rows(NotificationLog))[0].acknowledged_at is None, "acceptance commits before execution"
    assert (await rows(TelegramBotState))[0].next_offset == 101
    assert len(await rows(ChannelProviderMessage)) == 1, "callback recovers an ambiguous send receipt"
    restarted = TelegramService()
    await restarted.process_commands()
    await restarted.process_command(command_id)
    assert await accept(case, payload) == ("accepted", command_id)
    assert len(await rows(ChannelEvent)) == 1
    assert len(await rows(ChannelActionCommand)) == 1
    [log] = await rows(NotificationLog)
    assert log.acknowledged_by == "telegram:42"
    assert [a.action for a in await rows(AuditLog)].count("channel.action.applied") == 1
    assert all(t.used_at for t in await rows(ChannelActionToken))


@pytest.mark.parametrize(("user", "chat"), [(43, 123), (42, 999), (True, 123)])
async def test_wrong_user_or_chat_cannot_apply_actions(telegram_delivery, user, chat):
    result, command_id = await accept(telegram_delivery, await callback(telegram_delivery, user=user, chat=chat))
    assert result == "denied"
    assert command_id is None
    assert await rows(ChannelActionCommand) == []
    assert (await rows(NotificationLog))[0].acknowledged_at is None


@pytest.mark.parametrize("change", ["disable", "remove_actor", "different_chat", "different_bot", "disable_actions"])
async def test_current_channel_policy_revokes_old_buttons(telegram_delivery, change):
    case = telegram_delivery
    payload = await callback(case)
    async with get_session_factory()() as session:
        channel = await session.get(Channel, case["channel"])
        cfg = dict(channel.config)
        if change == "disable":
            channel.enabled = False
        elif change == "remove_actor":
            cfg["allowed_user_ids"] = [43]
        elif change == "different_chat":
            cfg["chat_id"] = "999"
        elif change == "different_bot":
            cfg["bot_token"] = "another-bot"
        else:
            cfg["inline_actions"] = False
        channel.config = cfg
        await session.commit()
    assert (await accept(case, payload))[0] == "denied"
    assert await rows(ChannelActionCommand) == []


async def test_allowlist_is_not_bypassed_by_any_chat_member(telegram_delivery):
    case = telegram_delivery
    async with get_session_factory()() as session:
        channel = await session.get(Channel, case["channel"])
        channel.config = {**channel.config, "any_chat_member": True}
        await session.commit()
    assert (await accept(case, await callback(case, user=43)))[0] == "denied"


async def test_expired_and_used_tokens_cannot_create_another_command(telegram_delivery):
    case = telegram_delivery
    payload = await callback(case)
    async with get_session_factory()() as session:
        token = await session.get(ChannelActionToken, payload["callback_query"]["data"][2:])
        token.expires_at = utc_now() - timedelta(seconds=2)
        await session.commit()
    assert (await accept(case, payload))[0] == "expired"
    assert await rows(ChannelActionCommand) == []


async def test_snooze_is_applied_once_without_extending_on_retry(telegram_delivery):
    case = telegram_delivery
    payload = await callback(case, "snooze_1h")
    _, command_id = await accept(case, payload)
    [command] = await rows(ChannelActionCommand)
    deadline = command.snooze_until
    # Crash after staging a snooze but before transaction commit/audit.
    with patch("app.core.channel_actions.record_change", side_effect=RuntimeError("crash")):
        await case["service"].process_command(command_id)
    assert await rows(Snooze) == []
    [command] = await rows(ChannelActionCommand)
    assert command.state == "pending"
    assert command.attempts == 1
    await make_command_due(command_id)
    restarted = TelegramService()
    await restarted.process_commands()
    await restarted.process_command(command_id)
    assert (await accept(case, {**payload, "update_id": 101}))[0] == "used"
    [snooze] = await rows(Snooze)
    assert snooze.target == "alarm"
    assert snooze.scope.value == "type"
    assert snooze.until == deadline
    assert snooze.created_by == "telegram:42"


async def test_provider_feedback_retries_without_reapplying_action(telegram_delivery):
    case = telegram_delivery
    _, command_id = await accept(case, await callback(case))
    await case["service"].process_command(command_id)
    await case["service"].enqueue_feedback()
    [feedback] = await rows(ChannelProviderCommand)
    with patch("app.core.telegram_service.call_bot", side_effect=TelegramAPIError(503)):
        await case["service"].process_feedback()
    [feedback] = await rows(ChannelProviderCommand)
    assert feedback.state == "pending"
    assert feedback.attempts == 1
    assert (await rows(ChannelActionCommand))[0].state == "applied"
    async with get_session_factory()() as session:
        f = await session.get(ChannelProviderCommand, feedback.id)
        f.next_attempt_at = utc_now() - timedelta(seconds=2)
        await session.commit()
    with patch("app.core.telegram_service.call_bot", new_callable=AsyncMock, return_value=True) as api:
        await TelegramService().process_feedback()
        assert api.await_args.args[1] == "editMessageReplyMarkup"
        assert api.await_args.args[2]["reply_markup"] == {"inline_keyboard": []}
    assert (await rows(ChannelProviderCommand))[0].state == "sent"
    assert len([a for a in await rows(AuditLog) if a.action == "channel.action.applied"]) == 1


async def test_http_ack_also_schedules_durable_button_cleanup(telegram_delivery):
    case = telegram_delivery
    async with get_session_factory()() as session:
        delivery = await session.get(Delivery, case["delivery"])
        await channel_actions.record_provider_reference(session, delivery, {
            "provider": "telegram", "bot_key": case["key"], "chat_id": "123", "message_id": 9,
            "view_url": "https://klopot.example/admin/#/log?id=ntf_telegram",
        })
        await session.commit()
    async with get_session_factory()() as session:
        await acknowledge_notification(session, case["log"], "admin")
        await session.commit()
    restarted = TelegramService()
    await restarted.enqueue_feedback()
    await restarted.enqueue_feedback()
    assert len(await rows(ChannelProviderCommand)) == 1
    with patch("app.core.telegram_service.call_bot", new_callable=AsyncMock, return_value=True) as api:
        await restarted.process_feedback()
        buttons = api.await_args.args[2]["reply_markup"]["inline_keyboard"]
        assert buttons[0][0]["url"].startswith("https://klopot.example/")
        assert "callback_data" not in buttons[0][0]


async def test_poll_cursor_is_durable_before_next_request(telegram_delivery):
    case = telegram_delivery
    payload = await callback(case)
    calls = []

    async def api(token, method, body, **kwargs):
        calls.append((method, body))
        if method == "getUpdates":
            return [payload] if len(calls) == 1 else []
        return True

    with patch("app.core.telegram_service.call_bot", side_effect=api):
        await case["service"].poll_once(case["key"], case["config"])
        await TelegramService().poll_once(case["key"], case["config"])
    assert [body for method, body in calls if method == "getUpdates"][1]["offset"] == 101
    assert any(method == "answerCallbackQuery" for method, _ in calls)
    assert (await rows(NotificationLog))[0].acknowledged_at is not None


async def test_snooze_until_morning_uses_local_calendar_across_dst(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(channel_actions, "get_settings", lambda: SimpleNamespace(tz="Europe/Bucharest", snooze_morning_hour=8))
    # Spring transition happens before 08:00; the target uses the new UTC offset.
    assert channel_actions.snooze_deadline("snooze_morning", datetime(2026, 3, 28, 23, 30)) == datetime(2026, 3, 29, 5)
    assert channel_actions.snooze_deadline("snooze_morning", datetime(2026, 3, 29, 6)) == datetime(2026, 3, 30, 5)


async def test_the_morning_hour_is_a_setting_and_the_button_says_it(monkeypatch):
    """Pre-open-source audit: 08:00 was written in the deadline and again in the
    button labels; one setting now drives both."""
    from app.channels.telegram_config import action_labels
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "tz", "UTC")
    monkeypatch.setattr(get_settings(), "snooze_morning_hour", 6)
    assert channel_actions.snooze_deadline("snooze_morning", datetime(2026, 7, 1, 5, 59)) == datetime(2026, 7, 1, 6)
    assert channel_actions.snooze_deadline("snooze_morning", datetime(2026, 7, 1, 6, 0)) == datetime(2026, 7, 2, 6)
    assert action_labels("en")["snooze_morning"] == "Snooze until 06:00"
    assert action_labels("ro")["snooze_morning"] == "Amână până la 06:00"
    assert action_labels("xx")["ack"] == "Acknowledge"


async def test_idle_bot_does_not_filter_randomized_update_ids(telegram_delivery):
    case = telegram_delivery
    async with get_session_factory()() as session:
        state = await session.get(TelegramBotState, case["key"])
        state.next_offset = 999999
        state.last_update_at = utc_now() - timedelta(days=8)
        await session.commit()
    with patch("app.core.telegram_service.call_bot", new_callable=AsyncMock, return_value=[]) as api:
        await case["service"].poll_once(case["key"], case["config"])
    assert "offset" not in api.await_args.args[2]


async def test_one_poller_per_bot_and_stop_cleans_up(telegram_delivery, make_channel):
    case = telegram_delivery
    async with get_session_factory()() as session:
        session.add(make_channel(name="same_bot", kind="telegram", config=case["config"]))
        await session.commit()
    started = asyncio.Event()

    async def poll(key):
        started.set()
        await asyncio.Event().wait()

    with patch.object(case["service"], "_poll", side_effect=poll) as receiver:
        await case["service"].sync_bots()
        await started.wait()
        await case["service"].sync_bots()
        assert receiver.call_count == 1
        assert len(case["service"]._pollers) == 1
        await case["service"].stop()
    assert case["service"]._pollers == {}


async def test_retention_waits_for_local_action_and_provider_cleanup(telegram_delivery):
    case = telegram_delivery
    _, command_id = await accept(case, await callback(case))
    async with get_session_factory()() as session:
        log = await session.get(NotificationLog, case["log"])
        log.fired_at = utc_now() - timedelta(days=400)
        delivery = await session.get(Delivery, case["delivery"])
        delivery.state = DeliveryState.sent
        await session.commit()
    await RetentionService()._sweep()
    assert len(await rows(NotificationLog)) == 1
    await case["service"].process_command(command_id)
    await RetentionService()._sweep()
    assert len(await rows(NotificationLog)) == 1, "cleanup must first be materialized"
    await case["service"].enqueue_feedback()
    await RetentionService()._sweep()
    assert len(await rows(NotificationLog)) == 1, "pending provider operation is retained"
    with patch("app.core.telegram_service.call_bot", new_callable=AsyncMock, return_value=True):
        await case["service"].process_feedback()
    await RetentionService()._sweep()
    assert await rows(NotificationLog) == []
    assert await rows(ChannelActionCommand) == []
    assert await rows(ChannelProviderCommand) == []


async def test_provider_already_cleared_is_success(telegram_delivery):
    case = telegram_delivery
    _, command_id = await accept(case, await callback(case))
    await case["service"].process_command(command_id)
    await case["service"].enqueue_feedback()
    with patch("app.core.telegram_service.call_bot", side_effect=TelegramAPIError(400, not_modified=True)):
        await case["service"].process_feedback()
    assert (await rows(ChannelProviderCommand))[0].state == "sent"


async def test_resolved_notification_buttons_cannot_snooze(telegram_delivery):
    case = telegram_delivery
    async with get_session_factory()() as session:
        log = await session.get(NotificationLog, case["log"])
        log.incident_event = "resolved"
        await session.commit()
    assert (await accept(case, await callback(case, "snooze_1h")))[0] == "resolved"
    assert await rows(ChannelActionCommand) == []


async def test_worker_sends_persisted_keyboard_and_records_provider_receipt(telegram_delivery):
    case = telegram_delivery
    receipt = {"provider": "telegram", "bot_key": case["key"], "chat_id": "123", "message_id": 77}
    with patch("app.channels.telegram.TelegramChannel.send", new_callable=AsyncMock,
               return_value=SendResult(ok=True, response=receipt)) as send:
        await DeliveryWorker().tick()
    config = send.await_args.args[1]
    assert config["_action_keyboard"] == (await rows(Delivery))[0].action_keyboard
    assert (await rows(ChannelProviderMessage))[0].message_id == 77
    assert (await rows(Delivery))[0].state == DeliveryState.sent


@pytest.mark.mysql
async def test_duplicate_callbacks_and_workers_do_not_duplicate_snooze(telegram_delivery):
    case = telegram_delivery
    payload = await callback(case, "snooze_1h")
    accepted = await asyncio.gather(accept(case, payload), accept(case, payload))
    assert accepted[0] == accepted[1]
    command_id = accepted[0][1]
    await asyncio.gather(TelegramService().process_command(command_id), TelegramService().process_command(command_id))
    assert len(await rows(ChannelActionCommand)) == 1
    assert len(await rows(ChannelEvent)) == 1
    assert len(await rows(Snooze)) == 1
