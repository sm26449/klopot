"""Dedicated Telegram bot polling and durable action/provider command workers.

One polling task per resolved bot identity, shared by all its channels. No
webhook is registered or deleted. Actions remain disabled until explicitly
enabled on a channel with an actor policy.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from ..channels._secrets import resolve_secret
from ..channels.telegram_config import action_labels, bot_key, validate_actions_config
from ..db import get_session_factory
from ..db.models import (
    Channel,
    ChannelActionCommand,
    ChannelActionToken,
    ChannelProviderCommand,
    ChannelProviderMessage,
    Delivery,
    Incident,
    NotificationLog,
    TelegramBotState,
)
from ..metrics import CHANNEL_COMMANDS_TOTAL
from ..utils.telegram_api import TelegramAPIError, api_url, call_bot
from ..utils.time import utc_now
from . import channel_actions, outbox

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._pollers: dict[str, asyncio.Task[None]] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        self._errors: dict[str, str | None] = {}
        self._last_poll: dict[str, float] = {}
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="telegram-actions")

    def is_alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        self._stop.set()
        tasks = list(self._pollers.values())
        if self._task is not None:
            tasks.append(self._task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._pollers.clear()
        self._configs.clear()
        self._task = None

    async def _run(self) -> None:
        sync_at = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() >= sync_at:
                    await self.sync_bots()
                    sync_at = time.monotonic() + 10
                await self.process_commands()
                await self.enqueue_feedback()
                await self.process_feedback()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram action worker cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=1)
            except TimeoutError:
                pass

    async def sync_bots(self) -> None:
        async with get_session_factory()() as session:
            rows = (await session.execute(select(Channel).where(
                Channel.kind == "telegram", Channel.enabled.is_(True),
            ).order_by(Channel.id))).scalars().all()
        wanted: dict[str, dict[str, Any]] = {}
        for channel in rows:
            cfg = dict(channel.config or {})
            if cfg.get("inline_actions") is not True:
                continue
            try:
                validate_actions_config(cfg)
            except ValueError:
                continue
            token = resolve_secret(cfg, "bot_token", "bot_token_ref")
            if token:
                wanted.setdefault(bot_key(token), cfg)
        self._configs = wanted
        for key in list(self._pollers):
            if key not in wanted or self._pollers[key].done():
                self._pollers[key].cancel()
                await asyncio.gather(self._pollers.pop(key), return_exceptions=True)
        for key in wanted:
            if key not in self._pollers:
                self._pollers[key] = asyncio.create_task(self._poll(key), name="telegram-poller")

    async def ensure_state(self, key: str) -> None:
        async with get_session_factory()() as session:
            if await session.get(TelegramBotState, key) is None:
                session.add(TelegramBotState(bot_key=key, next_offset=0))
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()  # another starter already created it

    async def _poll(self, key: str) -> None:
        while not self._stop.is_set() and key in self._configs:
            try:
                await self.poll_once(key, self._configs[key])
                self._errors[key] = None
                self._last_poll[key] = time.time()
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._errors[key] = str(error) if isinstance(error, TelegramAPIError) else "Telegram receiver processing failed"
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=5)
                except TimeoutError:
                    pass

    async def poll_once(self, key: str, config: dict[str, Any]) -> int:
        """Fetch and process one batch of callback queries for one bot.

        ``key`` is the bot identity derived from the resolved token in
        ``config`` (a mismatch raises ValueError). Uses the persisted offset,
        dropped after seven days without updates (Telegram re-randomises it).
        Each update is stored before its action command is applied; a failed
        callback answer never undoes a recorded action. Returns the number of
        updates processed; an invalid batch or update raises ValueError, and
        provider or processing errors propagate to the polling loop.
        """
        token = resolve_secret(config, "bot_token", "bot_token_ref")
        if not token or bot_key(token) != key:
            raise ValueError("Telegram bot identity unavailable")
        await self.ensure_state(key)
        async with get_session_factory()() as session:
            state = await session.get(TelegramBotState, key)
            assert state is not None
            offset = state.next_offset
            # Telegram randomises the next update id after a week of inactivity.
            idle = state.last_update_at and state.last_update_at < utc_now() - timedelta(days=7)
        request: dict[str, Any] = {"timeout": 25, "limit": 100, "allowed_updates": ["callback_query"]}
        if offset and not idle:
            request["offset"] = offset
        base = api_url(config)
        updates = await call_bot(token, "getUpdates", request, base_url=base, io_timeout=30)
        if not isinstance(updates, list) or len(updates) > 100:
            raise ValueError("invalid Telegram update batch")
        processed = 0
        for update in updates:
            if not isinstance(update, dict):
                raise ValueError("invalid Telegram update")
            async with get_session_factory()() as session:
                result, command_id = await channel_actions.ingest_update(session, key, update)
                await session.commit()
            if command_id:
                await self.process_command(command_id)
            callback = update.get("callback_query") or {}
            if isinstance(callback, dict) and isinstance(callback.get("id"), str) and len(callback["id"]) <= 128:
                text = "Action recorded" if result == "accepted" else {
                    "denied": "Not allowed", "expired": "Button expired", "used": "Already handled",
                    "resolved": "Incident already resolved", "invalid": "Invalid action",
                }.get(result, "No action")
                if command_id:
                    async with get_session_factory()() as session:
                        command = await session.get(ChannelActionCommand, command_id)
                        if command and command.state == "applied":
                            text = "Acknowledged" if command.action == "ack" else "Snoozed"
                        elif command and command.state == "failed":
                            text = "Action failed; check Klopot audit"
                try:
                    await call_bot(token, "answerCallbackQuery",
                                   {"callback_query_id": callback["id"], "text": text, "cache_time": 0}, base_url=base)
                except TelegramAPIError:
                    pass  # transient UI feedback never rolls back the durable action
            processed += 1
        return processed

    async def process_command(self, command_id: str) -> None:
        try:
            async with get_session_factory()() as session:
                applied = await channel_actions.apply_command(session, command_id)
                command = await session.get(ChannelActionCommand, command_id) if applied else None
                await session.commit()
                if command is not None:
                    CHANNEL_COMMANDS_TOTAL.labels(queue="actions", state=command.state).inc()
        except Exception:
            async with get_session_factory()() as session:
                command = (await session.execute(select(ChannelActionCommand).where(
                    ChannelActionCommand.id == command_id, ChannelActionCommand.state == "pending",
                ).with_for_update())).scalar_one_or_none()
                if command is not None:
                    command.attempts += 1
                    command.last_error = "local action transaction failed"
                    if command.attempts >= outbox.MAX_ATTEMPTS:
                        command.state = "failed"
                        command.next_attempt_at = None
                    else:
                        command.next_attempt_at = utc_now() + timedelta(seconds=outbox.backoff_seconds(command.attempts))
                    await session.commit()
                    if command.state == "failed":
                        CHANNEL_COMMANDS_TOTAL.labels(queue="actions", state="failed").inc()

    async def process_commands(self) -> None:
        async with get_session_factory()() as session:
            ids = list((await session.execute(select(ChannelActionCommand.id).where(
                ChannelActionCommand.state == "pending", ChannelActionCommand.next_attempt_at <= utc_now(),
            ).order_by(ChannelActionCommand.created_at).limit(20))).scalars())
        for ident in ids:
            await self.process_command(ident)

    async def enqueue_feedback(self) -> None:
        has_operation = select(ChannelProviderCommand.id).where(
            ChannelProviderCommand.reference_id == ChannelProviderMessage.id,
        ).exists()
        live_token = select(ChannelActionToken.id).where(
            ChannelActionToken.delivery_id == Delivery.id, ChannelActionToken.used_at.is_(None),
            ChannelActionToken.expires_at > utc_now(),
        ).exists()
        has_token = select(ChannelActionToken.id).where(ChannelActionToken.delivery_id == Delivery.id).exists()
        done = or_(NotificationLog.acknowledged_at.is_not(None), Incident.acknowledged_at.is_not(None),
                   Incident.resolved_at.is_not(None), ~live_token)
        async with get_session_factory()() as session:
            refs = (await session.execute(select(ChannelProviderMessage.id).join(
                Delivery, ChannelProviderMessage.delivery_id == Delivery.id,
            ).join(NotificationLog, Delivery.notification_id == NotificationLog.id).outerjoin(
                Incident, NotificationLog.incident_id == Incident.id,
            ).where(ChannelProviderMessage.provider == "telegram", has_token,
                    ~has_operation, done).limit(50))).scalars().all()
            for ident in refs:
                session.add(ChannelProviderCommand(reference_id=ident, operation="clear_actions", state="pending",
                                                    attempts=0, next_attempt_at=utc_now().replace(microsecond=0)))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()  # concurrent enqueue; unique operation wins

    async def process_feedback(self) -> None:
        async with get_session_factory()() as session:
            ids = list((await session.execute(select(ChannelProviderCommand.id).where(
                ChannelProviderCommand.state == "pending", ChannelProviderCommand.next_attempt_at <= utc_now(),
            ).order_by(ChannelProviderCommand.id).limit(20))).scalars())
        for ident in ids:
            await self.feedback_one(ident)

    async def feedback_one(self, ident: int) -> None:
        """One attempt at a queued reply-markup update (removing the buttons).

        Skips a command that is absent, not pending, not due yet or locked by
        another worker. Uses the delivery's saved config and checks the bot
        identity. A successful edit — "not modified" included — completes it;
        a 400/401/403/404, missing credentials or the last attempt fails it;
        any other Telegram error reschedules it with the outbox backoff. The
        outcome is committed before the metric counts it.
        """
        async with get_session_factory()() as session:
            command = (await session.execute(select(ChannelProviderCommand).where(
                ChannelProviderCommand.id == ident, ChannelProviderCommand.state == "pending",
                ChannelProviderCommand.next_attempt_at <= utc_now(),
            ).with_for_update(skip_locked=True))).scalar_one_or_none()
            if command is None:
                return
            ref = await session.get(ChannelProviderMessage, command.reference_id)
            delivery = await session.get(Delivery, ref.delivery_id) if ref else None
            cfg = dict(delivery.effective_config or {}) if delivery else {}
            token = resolve_secret(cfg, "bot_token", "bot_token_ref")
            command.attempts += 1
            if not ref or not token or bot_key(token) != ref.bot_key:
                command.state = "failed"
                command.last_error = "bot credentials unavailable or changed"
                command.next_attempt_at = None
            else:
                rows = []
                if ref.view_url:
                    labels = action_labels(cfg.get("actions_locale"))
                    rows = [[{"text": labels["view"], "url": ref.view_url}]]
                try:
                    await call_bot(token, "editMessageReplyMarkup", {
                        "chat_id": ref.chat_id, "message_id": ref.message_id,
                        "reply_markup": {"inline_keyboard": rows},
                    }, base_url=api_url(cfg))
                    command.state = "sent"
                    command.next_attempt_at = None
                    command.last_error = None
                except TelegramAPIError as error:
                    if error.not_modified:
                        command.state = "sent"
                        command.next_attempt_at = None
                        command.last_error = None
                    elif error.status in (400, 401, 403, 404) or command.attempts >= outbox.MAX_ATTEMPTS:
                        command.state = "failed"
                        command.next_attempt_at = None
                        command.last_error = str(error)
                    else:
                        command.next_attempt_at = utc_now() + timedelta(seconds=outbox.backoff_seconds(command.attempts))
                        command.last_error = str(error)
            await session.commit()

            if command.state in ("sent", "failed"):
                CHANNEL_COMMANDS_TOTAL.labels(queue="provider", state=command.state).inc()

    def health(self, config: dict[str, Any]) -> dict[str, Any]:
        if config.get("inline_actions") is not True:
            return {"enabled": False}
        try:
            validate_actions_config(config)
        except ValueError as error:
            return {"enabled": True, "connected": False, "error": str(error)}
        token = resolve_secret(config, "bot_token", "bot_token_ref")
        if not token:
            return {"enabled": True, "connected": False, "error": "Bot token unavailable"}
        key = bot_key(token)
        task = self._pollers.get(key)
        return {"enabled": True, "connected": bool(task and not task.done() and key in self._last_poll and not self._errors.get(key)),
                "last_poll_ts": self._last_poll.get(key), "error": self._errors.get(key)}


_service: TelegramService | None = None


def get_telegram_service() -> TelegramService:
    global _service
    if _service is None:
        _service = TelegramService()
    return _service
