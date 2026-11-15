"""Durable Telegram capabilities, provider inbox and transactional local actions."""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import record_change
from ..auth import Actor
from ..channels._secrets import resolve_secret
from ..channels.telegram_config import (
    LABELS,
    actor_allowed,
    allowed_users,
    bot_key,
    numeric_id,
    public_view_url,
    validate_actions_config,
)
from ..config import get_settings
from ..db.models import (
    Channel,
    ChannelActionCommand,
    ChannelActionToken,
    ChannelEvent,
    ChannelProviderMessage,
    Delivery,
    Incident,
    NotificationLog,
    Snooze,
    SnoozeScope,
    TelegramBotState,
)
from ..utils.time import utc_now
from .notification_actions import acknowledge_notification

TOKEN_TTL = timedelta(hours=24)
ACTIONS = ("ack", "snooze_1h", "snooze_morning")


def issue_tokens(delivery: Delivery, config: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    if config.get("inline_actions") is not True:
        return None
    validate_actions_config(config)
    secret = resolve_secret(config, "bot_token", "bot_token_ref")
    if not secret:
        return None
    labels = LABELS[config.get("actions_locale", "en")]
    buttons = []
    for action in ACTIONS:
        token = ChannelActionToken(
            id=secrets.token_urlsafe(24), action=action, bot_key=bot_key(secret),
            chat_id=str(config["chat_id"]), allowed_user_ids=allowed_users(config),
            any_chat_member=config.get("any_chat_member") is True,
            expires_at=(now + TOKEN_TTL).replace(microsecond=0),
        )
        delivery.action_tokens.append(token)
        buttons.append({"text": labels[action], "callback_data": "k:" + token.id})
    return {"inline_keyboard": [buttons[:2], buttons[2:]]}


async def record_provider_reference(session: AsyncSession, delivery: Delivery, response: dict[str, Any]) -> None:
    # Generic: a channel that reports its message id (ntfy …) — migration 0028.
    ref = response.get("provider_ref")
    if isinstance(ref, str) and ref:
        delivery.provider_ref = ref[:255]
    if response.get("provider") != "telegram":
        return
    chat = numeric_id(response.get("chat_id"))
    message = numeric_id(response.get("message_id"), positive=True)
    key = response.get("bot_key")
    if chat is None or message is None or not isinstance(key, str) or len(key) != 64:
        return
    # Sync first attempts and callback receipt binding share this lock order.
    await session.execute(select(Delivery.id).where(Delivery.id == delivery.id).with_for_update())
    existing = (await session.execute(select(ChannelProviderMessage).where(
        ChannelProviderMessage.provider == "telegram", ChannelProviderMessage.bot_key == key,
        ChannelProviderMessage.chat_id == chat, ChannelProviderMessage.message_id == int(message),
    ).with_for_update())).scalar_one_or_none()
    if existing is None:
        session.add(ChannelProviderMessage(
            delivery_id=delivery.id, provider="telegram", bot_key=key,
            chat_id=chat, message_id=int(message), view_url=response.get("view_url"),
        ))
    elif existing.delivery_id != delivery.id:
        raise ValueError("Telegram receipt already belongs to another delivery")
    elif existing.view_url is None and response.get("view_url"):
        existing.view_url = response["view_url"]


def snooze_deadline(action: str, now: datetime) -> datetime | None:
    if action == "snooze_1h":
        return (now + timedelta(hours=1)).replace(microsecond=0)
    if action != "snooze_morning":
        return None
    zone = ZoneInfo(get_settings().tz)
    local = now.replace(tzinfo=UTC).astimezone(zone)
    date = local.date()
    if local.time() >= time(8):
        date += timedelta(days=1)
    return datetime.combine(date, time(8), tzinfo=zone).astimezone(UTC).replace(tzinfo=None, microsecond=0)


async def ingest_update(session: AsyncSession, key: str, payload: dict[str, Any]) -> tuple[str, str | None]:
    """Commit inbox, cursor and command together. Caller commits before answering Telegram."""
    update_id = payload.get("update_id")
    if isinstance(update_id, bool) or not isinstance(update_id, int) or not 0 <= update_id < 2**63 - 1:
        raise ValueError("invalid Telegram update_id")
    state = (await session.execute(select(TelegramBotState).where(
        TelegramBotState.bot_key == key,
    ).with_for_update())).scalar_one()
    existing = await session.get(ChannelEvent, (key, update_id))
    if existing is not None:
        return existing.result, existing.command_id
    event = ChannelEvent(bot_key=key, update_id=update_id, result="ignored")
    session.add(event)
    state.next_offset = update_id + 1
    state.last_update_at = utc_now().replace(microsecond=0)
    callback = payload.get("callback_query")
    if not isinstance(callback, dict):
        return event.result, None
    data = callback.get("data")
    message = callback.get("message")
    sender = callback.get("from")
    if not isinstance(data, str) or not data.startswith("k:") or len(data) > 64 or not isinstance(message, dict) or not isinstance(sender, dict):
        event.result = "invalid"
        return event.result, None
    token = await session.get(ChannelActionToken, data[2:])
    user = numeric_id(sender.get("id"), positive=True)
    chat = numeric_id((message.get("chat") or {}).get("id")) if isinstance(message.get("chat"), dict) else None
    message_id = numeric_id(message.get("message_id"), positive=True)
    if token is None or user is None or chat is None or message_id is None or token.bot_key != key or token.chat_id != chat:
        event.result = "denied"
        return event.result, None
    # Match the delivery worker's lock order. No local action is applied here.
    delivery = (await session.execute(select(Delivery).where(
        Delivery.id == token.delivery_id,
    ).with_for_update())).scalar_one_or_none()
    if delivery is None:
        event.result = "expired"
        return event.result, None
    token = (await session.execute(select(ChannelActionToken).where(
        ChannelActionToken.id == token.id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one()
    channel = (await session.execute(select(Channel).where(Channel.name == delivery.channel))).scalar_one_or_none()
    snapshot = {"allowed_user_ids": token.allowed_user_ids, "any_chat_member": token.any_chat_member}
    allowed = False
    if channel is not None and channel.enabled and channel.kind.value == "telegram" and channel.config.get("inline_actions") is True:
        current_token = resolve_secret(channel.config, "bot_token", "bot_token_ref")
        allowed = bool(current_token and bot_key(current_token) == key and numeric_id(channel.config.get("chat_id")) == chat
                       and actor_allowed(snapshot, user) and actor_allowed(channel.config, user))
    actor = Actor(kind="system", id=None, name=f"telegram:{user}", scopes=frozenset({"ack"}))
    if not allowed:
        event.result = "denied"
        await record_change(session, actor, "channel.action.denied", resource_kind="delivery", resource_id=str(delivery.id))
        return event.result, None
    if token.expires_at <= utc_now():
        event.result = "expired"
        return event.result, None
    if token.used_at is not None:
        event.result = "used"
        return event.result, None
    log = await session.get(NotificationLog, delivery.notification_id)
    incident = await session.get(Incident, log.incident_id) if log and log.incident_id else None
    if log is None or log.is_test or log.incident_event == "resolved" or (incident and incident.resolved_at is not None):
        event.result = "resolved"
        return event.result, None
    prior = (await session.execute(select(ChannelActionCommand).where(
        ChannelActionCommand.delivery_id == delivery.id,
    ))).scalar_one_or_none()
    if prior is not None:
        event.result = "used"
        return event.result, prior.id
    # A verified callback can bind a receipt lost after an ambiguous send timeout.
    ref = (await session.execute(select(ChannelProviderMessage).where(
        ChannelProviderMessage.provider == "telegram", ChannelProviderMessage.bot_key == key,
        ChannelProviderMessage.chat_id == chat, ChannelProviderMessage.message_id == int(message_id),
    ).with_for_update())).scalar_one_or_none()
    if ref is not None and ref.delivery_id != delivery.id:
        event.result = "denied"
        return event.result, None
    if ref is None:
        session.add(ChannelProviderMessage(delivery_id=delivery.id, provider="telegram", bot_key=key,
                                           chat_id=chat, message_id=int(message_id),
                                           view_url=public_view_url(delivery.effective_config or {}, log.id, log.incident_id)))
    now = utc_now().replace(microsecond=0)
    command = ChannelActionCommand(
        id="act_" + uuid.uuid4().hex, delivery_id=delivery.id, action=token.action,
        actor_name=actor.name, snooze_until=snooze_deadline(token.action, now),
        state="pending", attempts=0, next_attempt_at=now,
    )
    session.add(command)
    await session.flush()
    await session.execute(update(ChannelActionToken).where(
        ChannelActionToken.delivery_id == delivery.id,
    ).values(used_at=now))
    event.result = "accepted"
    event.command_id = command.id
    await record_change(session, actor, "channel.action.accepted", resource_kind="delivery", resource_id=str(delivery.id),
                        after={"action": command.action, "command_id": command.id})
    return event.result, command.id


async def apply_command(session: AsyncSession, command_id: str) -> bool:
    command = (await session.execute(select(ChannelActionCommand).where(
        ChannelActionCommand.id == command_id, ChannelActionCommand.state == "pending",
        ChannelActionCommand.next_attempt_at <= utc_now(),
    ).with_for_update(skip_locked=True))).scalar_one_or_none()
    if command is None:
        return False
    command.attempts += 1
    delivery = await session.get(Delivery, command.delivery_id)
    log = await session.get(NotificationLog, delivery.notification_id) if delivery else None
    if log is None or delivery is None:
        command.state = "failed"
        command.last_error = "notification no longer available"
        return True
    actor = Actor(kind="system", id=None, name=command.actor_name, scopes=frozenset({"ack"}))
    if command.action == "ack":
        await acknowledge_notification(session, log.id, actor.name)
    elif command.action in ("snooze_1h", "snooze_morning") and command.snooze_until:
        if command.snooze_until > utc_now():
            session.add(Snooze(scope=SnoozeScope.type, target=log.type, until=command.snooze_until,
                               reason="Telegram action", created_by=actor.name))
    else:
        command.state = "failed"
        command.last_error = "unsupported channel action"
        return True
    command.state = "applied"
    command.applied_at = utc_now().replace(microsecond=0)
    command.next_attempt_at = None
    command.last_error = None
    await record_change(session, actor, "channel.action.applied", resource_kind="delivery", resource_id=str(delivery.id),
                        after={"action": command.action, "command_id": command.id, "until": command.snooze_until})
    return True
