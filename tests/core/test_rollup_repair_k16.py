"""A notification whose channels have all settled never stays "pending" (review K16).

Resolving an incident and settling a delivery each write the notification's
rollup from their own REPEATABLE-READ snapshot. When they race (the resolve
cancels one channel while the worker settles another), both can write
``pending`` although every channel is final: the row stays pending for good —
shown as in flight, and an identical fire within the dedup window coalesces
onto it and is dropped. Neither writer can lock the other's rows without a
deadlock (the resolve deliberately skips locked deliveries), so the worker
repairs such rows on every tick instead.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.delivery_worker import DeliveryWorker
from app.db.models import Delivery, DeliveryState, DeliveryStatus, NotificationLog, Severity
from app.utils.time import utc_now
from tests._db import fresh


async def _log(db_session, id_: str, states: list[DeliveryState]) -> None:
    db_session.add(NotificationLog(id=id_, type="t", severity=Severity.critical, title="x", fired_at=utc_now(),
                                   delivery_status=DeliveryStatus.pending, is_test=False))
    await db_session.flush()
    for i, state in enumerate(states):
        db_session.add(Delivery(notification_id=id_, channel=f"c{i}", purpose="notification", state=state,
                                attempts=1, idempotency_key=f"{id_}:c{i}"))
    await db_session.commit()


async def test_a_settled_notification_left_pending_is_repaired(db_engine, db_session):
    await _log(db_session, "ntf_lost", [DeliveryState.sent, DeliveryState.cancelled])
    await _log(db_session, "ntf_failed", [DeliveryState.failed, DeliveryState.cancelled])
    await _log(db_session, "ntf_inflight", [DeliveryState.sent, DeliveryState.pending])

    repaired = await DeliveryWorker().repair_rollups()

    assert repaired == 2
    await fresh(db_session)
    status = {r.id: r.delivery_status for r in (await db_session.execute(select(NotificationLog))).scalars()}
    assert status == {"ntf_lost": DeliveryStatus.sent, "ntf_failed": DeliveryStatus.failed,
                      "ntf_inflight": DeliveryStatus.pending}
    lost = await db_session.get(NotificationLog, "ntf_lost")
    assert lost.dispatched_to == ["c0"]
