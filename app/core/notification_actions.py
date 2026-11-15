"""Shared notification acknowledgement for HTTP and trusted channel commands."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Delivery, DeliveryState, Incident, NotificationLog
from ..utils.time import utc_now
from . import incidents, outbox


async def acknowledge_notification(session: AsyncSession, notification_id: str, actor: str) -> bool:
    log = await session.get(NotificationLog, notification_id)
    if log is None:
        return False
    if log.incident_id:
        incident = (await session.execute(select(Incident).where(
            Incident.id == log.incident_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if incident is not None:
            await incidents.acknowledge(session, incident, actor)
            return True
    log = (await session.execute(select(NotificationLog).where(
        NotificationLog.id == notification_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if log is None:
        return False
    if log.acknowledged_at is None:
        log.acknowledged_at = utc_now().replace(microsecond=0)
        log.acknowledged_by = actor
    await session.flush()
    now = utc_now()
    # Never wait for a delivery row (review K05): the worker locks its delivery
    # first and this notification row second, so a blocking UPDATE here — which
    # locks every delivery of the notification it scans — deadlocked with it
    # (1213). Skip what is locked, like incidents.stop_pending: the worker
    # rechecks the acknowledgement before every escalation attempt.
    pending = (await session.execute(select(Delivery).where(
        Delivery.notification_id == notification_id, Delivery.purpose == "escalation",
        Delivery.state == DeliveryState.pending,
        or_(Delivery.lease_until.is_(None), Delivery.lease_until < now),
    ).order_by(Delivery.id).with_for_update(skip_locked=True))).scalars().all()
    for delivery in pending:
        outbox.cancel_delivery(delivery)
    # Stop provider-side repeats (Pushover emergency receipts) — migration 0029.
    from .provider_lifecycle import enqueue_cancellations
    await enqueue_cancellations(session, notification_id=notification_id)
    return True
