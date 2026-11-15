"""DB-backed operational snapshots shared by the UI and Prometheus scrape."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    Channel,
    ChannelActionCommand,
    ChannelProviderCommand,
    ChannelProviderMessage,
    Delivery,
)
from ..schemas.operations import FailedOperation, OperationsRead, QueueSummary
from ..utils.redact import redact_url
from ..utils.time import utc_now

OVERDUE_SECONDS = 120


async def queue_summary(session: AsyncSession, model: Any, name: str) -> QueueSummary:
    now = utc_now()
    states = {str(getattr(state, "value", state)): count for state, count in (
        await session.execute(select(model.state, func.count()).group_by(model.state))
    ).all()}
    pending = model.state == "pending"
    unleased = or_(model.lease_until.is_(None), model.lease_until < now) if model is Delivery else true()
    oldest = (await session.execute(select(func.min(model.created_at)).where(pending))).scalar_one()
    overdue, due = (await session.execute(select(func.count(), func.min(model.next_attempt_at)).where(
        pending, unleased, model.next_attempt_at < now - timedelta(seconds=OVERDUE_SECONDS),
    ))).one()
    return QueueSummary(name=name, states=states, overdue=overdue,
                        oldest_pending_seconds=max(0.0, (now - oldest).total_seconds()) if oldest else 0.0,
                        oldest_overdue_seconds=max(0.0, (now - due).total_seconds()) if due else 0.0)


async def snapshot(session: AsyncSession) -> OperationsRead:
    from ..channels.manager import get_channel_manager
    from .delivery_worker import get_delivery_worker
    from .engine import get_engine
    from .provider_lifecycle import get_provider_lifecycle_service
    from .schedule_service import get_schedule_service
    from .telegram_service import get_telegram_service

    queues = []
    failures = []
    for model, name in ((Delivery, "deliveries"), (ChannelActionCommand, "actions"),
                        (ChannelProviderCommand, "provider")):
        queues.append(await queue_summary(session, model, name))
        query = select(model, Delivery.notification_id, Delivery.channel)
        if model is ChannelProviderCommand:
            query = query.join(ChannelProviderMessage, model.reference_id == ChannelProviderMessage.id).join(
                Delivery, ChannelProviderMessage.delivery_id == Delivery.id,
            )
        elif model is ChannelActionCommand:
            query = query.join(Delivery, model.delivery_id == Delivery.id)
        query = query.where(model.state == "failed").order_by(model.created_at.desc()).limit(10)
        for row, notification_id, channel in (await session.execute(query)).all():
            failures.append(FailedOperation(queue=name, notification_id=notification_id, channel=channel,
                                            attempts=row.attempts, error=redact_url(row.last_error)[:500] if row.last_error else None,
                                            created_at=row.created_at))
    channels = (await session.execute(select(Channel).where(Channel.enabled.is_(True)))).scalars().all()
    service = get_telegram_service()
    telegram = [{"channel": c.name, **service.health(c.config or {})} for c in channels
                if c.kind.value == "telegram" and (c.config or {}).get("inline_actions") is True]
    manager = get_channel_manager()
    mqtt = [{"channel": c.name, **manager.output_health(c.name, "mqtt")} for c in channels if c.kind.value == "mqtt"]
    return OperationsRead(queues=queues, workers={
        "engine": get_engine().is_alive(), "delivery": get_delivery_worker().is_alive(),
        "scheduler": get_schedule_service().is_alive(), "telegram": service.is_alive(),
        "lifecycle": get_provider_lifecycle_service().is_alive(),
    }, telegram=telegram, mqtt=mqtt,
        recent_failures=sorted(failures, key=lambda f: f.created_at, reverse=True)[:20])
