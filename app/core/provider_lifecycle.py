"""Generic provider lifecycle (roadmap §5): durable commands + inbound inbox.

Some providers keep a message "alive" after it is sent — a Pushover
emergency repeats until acknowledged. Two directions must stay in sync, each
applied exactly once:

- **Klopot → provider.** When an alert is acknowledged in Klopot (UI, API,
  Telegram button, any path through ``incidents.acknowledge`` or
  ``notification_actions.acknowledge_notification``), every open emergency
  receipt of it gets a ``lifecycle_commands`` row (``cancel_receipt``).
  The service runs due commands with backoff; the unique
  (delivery, action) makes a second acknowledgement a no-op.
- **Provider → Klopot.** Open receipts are polled; when one was acknowledged
  in the Pushover app, an ``inbound_events`` row (unique per receipt) is
  written and the alert is acknowledged in Klopot with actor
  ``pushover:<device>``. A repeated poll finds the event and does nothing.
  Expired receipts are recorded the same way and no longer polled.

Telegram keeps its own, richer tables (``channel_provider_*``); this module
is for providers whose reference is just a string (``deliveries.provider_ref``).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels import pushover
from ..db import get_session
from ..db.models import (
    Channel,
    Delivery,
    DeliveryState,
    InboundEvent,
    LifecycleCommand,
    NotificationLog,
)
from ..utils.time import utc_now

logger = logging.getLogger(__name__)

TICK_SEC = 30
POLL_EVERY_TICKS = 2                    # poll receipts every 60 s
BACKOFF_SEC = (30, 60, 300, 900, 1800, 3600)
MAX_ATTEMPTS = 8
RECEIPT_WINDOW = timedelta(seconds=10800 + 600)   # Pushover's max expire + slack
BATCH = 50


async def enqueue_cancellations(
    session: AsyncSession, *, notification_id: str | None = None, incident_id: str | None = None,
) -> int:
    """Queue ``cancel_receipt`` for the open emergency receipts of an
    acknowledged notification or incident. Idempotent."""
    if notification_id is None and incident_id is None:
        return 0
    query = select(Delivery).join(NotificationLog, NotificationLog.id == Delivery.notification_id).where(
        Delivery.provider_ref.like(f"{pushover.RECEIPT_PREFIX}%"),
    )
    query = query.where(NotificationLog.id == notification_id) if notification_id \
        else query.where(NotificationLog.incident_id == incident_id)
    deliveries = (await session.execute(query)).scalars().all()
    if not deliveries:
        return 0
    have = {d for (d,) in (await session.execute(select(LifecycleCommand.delivery_id).where(
        LifecycleCommand.delivery_id.in_([d.id for d in deliveries]),
        LifecycleCommand.action == "cancel_receipt",
    ))).all()}
    added = 0
    for d in deliveries:
        receipt = pushover.receipt_of(d.provider_ref)
        if receipt is None or d.id in have:
            continue
        try:
            async with session.begin_nested():
                session.add(LifecycleCommand(
                    delivery_id=d.id, provider="pushover", action="cancel_receipt", ref=receipt,
                    # NULL = due now. Not utc_now(): MySQL DATETIME *rounds*
                    # microseconds, which can store a moment in the future.
                    state="pending", next_attempt_at=None,
                ))
                await session.flush()
            added += 1
        except IntegrityError:
            pass   # a concurrent acknowledgement queued it already
    return added


async def _config_for(session: AsyncSession, delivery: Delivery) -> dict[str, Any]:
    """The config the message was sent with (frozen on the delivery), else the
    channel's current one."""
    if delivery.effective_config:
        return dict(delivery.effective_config)
    channel = (await session.execute(select(Channel).where(Channel.name == delivery.channel))).scalar_one_or_none()
    return dict(channel.config or {}) if channel else {}


async def run_due_commands(session: AsyncSession) -> int:
    """Execute due commands; returns how many were attempted. Caller commits."""
    now = utc_now()
    due = (await session.execute(
        select(LifecycleCommand).where(
            LifecycleCommand.state == "pending",
            or_(LifecycleCommand.next_attempt_at.is_(None), LifecycleCommand.next_attempt_at <= now),
        ).order_by(LifecycleCommand.id).limit(BATCH).with_for_update(skip_locked=True)
    )).scalars().all()
    for cmd in due:
        delivery = await session.get(Delivery, cmd.delivery_id)
        error = "delivery gone" if delivery is None else None
        if delivery is not None and cmd.action == "cancel_receipt":
            error = await pushover.cancel_receipt(await _config_for(session, delivery), cmd.ref)
        elif delivery is not None:
            error = f"unknown action {cmd.action}"
        cmd.attempts += 1
        cmd.updated_at = now
        if error is None:
            cmd.state, cmd.last_error, cmd.next_attempt_at = "done", None, None
        else:
            cmd.last_error = error[:500]
            if cmd.attempts >= MAX_ATTEMPTS:
                cmd.state, cmd.next_attempt_at = "failed", None
                logger.warning("lifecycle command %s %s failed for good: %s", cmd.action, cmd.ref, error)
            else:
                cmd.next_attempt_at = now + timedelta(seconds=BACKOFF_SEC[min(cmd.attempts - 1, len(BACKOFF_SEC) - 1)])
    return len(due)


def receipt_event_key(receipt: str) -> str:
    return f"receipt:{receipt}"


async def poll_receipts(session: AsyncSession) -> int:
    """Check open emergency receipts; acknowledge in Klopot what was
    acknowledged in the Pushover app. Returns the number acknowledged."""
    from .notification_actions import acknowledge_notification

    since = utc_now() - RECEIPT_WINDOW
    # Only receipts still open, filtered in SQL BEFORE the limit (review K13):
    # filtering acknowledged / closed ones after it let 50 of them fill every
    # batch, and newer receipts were never polled. A receipt's inbound event
    # key is "receipt:<id>" — the provider_ref without its "pushover:" head.
    event_key = literal("receipt:") + func.substr(Delivery.provider_ref, len(pushover.RECEIPT_PREFIX) + 1)
    closed = select(InboundEvent.id).where(
        InboundEvent.provider == "pushover", InboundEvent.event_key == event_key,
    ).exists()
    deliveries = (await session.execute(
        select(Delivery)
        .join(NotificationLog, NotificationLog.id == Delivery.notification_id)
        .where(
            Delivery.provider_ref.like(f"{pushover.RECEIPT_PREFIX}%"),
            Delivery.state == DeliveryState.sent, Delivery.created_at >= since,
            NotificationLog.acknowledged_at.is_(None), ~closed,
        ).order_by(Delivery.id).limit(BATCH)
    )).scalars().all()
    acknowledged = 0
    for delivery in deliveries:
        receipt = pushover.receipt_of(delivery.provider_ref)
        if receipt is None:
            continue
        status = await pushover.receipt_status(await _config_for(session, delivery), receipt)
        if status is None:
            continue
        if status.get("acknowledged") == 1:
            result = "acknowledged"
        elif status.get("expired") == 1:
            result = "expired"
        else:
            continue
        try:
            async with session.begin_nested():
                session.add(InboundEvent(provider="pushover", event_key=receipt_event_key(receipt), result=result))
                await session.flush()
        except IntegrityError:
            continue   # another poller recorded it first
        if result == "acknowledged":
            device = status.get("acknowledged_by_device") or "app"
            await acknowledge_notification(session, delivery.notification_id, f"pushover:{device}"[:64])
            acknowledged += 1
    return acknowledged


class ProviderLifecycleService:
    """Background loop: run due commands every tick, poll receipts every
    ``POLL_EVERY_TICKS`` ticks."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._ticks = 0

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="provider-lifecycle")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def is_alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def tick(self) -> None:
        self._ticks += 1
        async for session in get_session():
            await run_due_commands(session)
            if self._ticks % POLL_EVERY_TICKS == 0:
                await poll_receipts(session)
            await session.commit()
            break

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("provider lifecycle tick failed")
            await asyncio.sleep(TICK_SEC)


_service: ProviderLifecycleService | None = None


def get_provider_lifecycle_service() -> ProviderLifecycleService:
    global _service
    if _service is None:
        _service = ProviderLifecycleService()
    return _service
