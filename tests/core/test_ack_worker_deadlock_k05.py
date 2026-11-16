"""Acknowledging a notification never deadlocks with the delivery worker (review K05).

The worker locks a delivery row (its lease claim) and, once the send is done,
the notification row (first-success accounting). ``acknowledge_notification``
took the opposite order: the notification row, then a blocking UPDATE over the
notification's deliveries — which locks every row of that notification it
scans, the worker's included. On MySQL the two deadlocked (1213): the ack
answered 500, or the worker lost a send it had already made and retried it.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.notification_actions import acknowledge_notification
from app.db.models import Delivery, DeliveryState, NotificationLog, Severity
from app.utils.time import utc_now

pytestmark = pytest.mark.mysql


async def test_ack_while_a_worker_holds_a_sibling_delivery(db_session, make_template):
    from app.db import session as session_module

    tpl = make_template(severity=Severity.critical)
    db_session.add(tpl)
    await db_session.flush()
    log = NotificationLog(id="ntf_k05", template_id=tpl.id, type=tpl.type, severity=Severity.critical,
                          title="t", message="m", fired_at=utc_now(), dispatched_to=["ui"],
                          failed_channels={}, delivery_status="pending", is_test=False)
    db_session.add(log)
    await db_session.flush()
    sent = Delivery(notification_id=log.id, channel="ui", purpose="notification",
                    state=DeliveryState.pending, idempotency_key="ntf_k05:ui")
    escalation = Delivery(notification_id=log.id, channel="sms", purpose="escalation",
                          state=DeliveryState.pending, idempotency_key="ntf_k05:sms:esc")
    db_session.add_all([sent, escalation])
    await db_session.commit()
    sent_id, escalation_id = sent.id, escalation.id

    factory = session_module._session_factory
    async with factory() as worker, factory() as acker:
        # The worker claims its delivery (row lock held until it commits) …
        await worker.execute(update(Delivery).where(Delivery.id == sent_id)
                             .values(lease_until=utc_now() + timedelta(seconds=60)))

        async def ack() -> bool:
            done = await acknowledge_notification(acker, log.id, "operator")
            await acker.commit()
            return done

        acking = asyncio.create_task(ack())
        await asyncio.sleep(0.5)          # the ack now holds the notification row
        # … then, the send done, accounts the first success on the notification row.
        await worker.execute(update(NotificationLog).where(NotificationLog.id == log.id)
                             .values(success_counted=True))
        await worker.commit()
        assert await asyncio.wait_for(acking, timeout=10) is True

    async with factory() as s:
        rows = {d.id: d.state for d in (await s.execute(select(Delivery))).scalars().all()}
        acked = (await s.execute(select(NotificationLog).where(NotificationLog.id == log.id))).scalar_one()
    assert rows[escalation_id] == DeliveryState.cancelled
    assert acked.acknowledged_at is not None
    assert acked.success_counted is True
