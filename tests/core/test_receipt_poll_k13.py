"""The Pushover receipt poll reaches every open receipt (review K13).

The poll took the first 50 sent receipt deliveries of the last 3 h by id and
only then, in Python, dropped the ones already acknowledged or closed. With
50 such receipts in the window, newer ones were never polled: an
acknowledgement made in the Pushover app never reached Klopot and the SMS
escalation still went out. The filters are now part of the query.
"""
from __future__ import annotations

import pytest

from app.core import provider_lifecycle as pl
from app.db.models import Delivery, DeliveryState, DeliveryStatus, InboundEvent, NotificationLog, Severity
from app.utils.time import utc_now

pytestmark = pytest.mark.anyio

CONFIG = {"user_key": "u_key_1234", "app_token": "a_tok_1234"}


async def _receipts(db_session, n: int, *, acked: set[int], closed: set[int]) -> None:
    now = utc_now()
    for i in range(n):
        db_session.add(NotificationLog(
            id=f"ntf_{i:03d}", type="disk_full", severity=Severity.critical, title="x",
            delivery_status=DeliveryStatus.sent, is_test=False, fired_at=now,
            acknowledged_at=now if i in acked else None))
    await db_session.flush()
    for i in range(n):
        db_session.add(Delivery(
            notification_id=f"ntf_{i:03d}", channel="pager", purpose="notification",
            state=DeliveryState.sent, attempts=1, idempotency_key=f"k{i}", effective_config=CONFIG,
            effective_kind="pushover", provider_ref=f"{pl.pushover.RECEIPT_PREFIX}R{i}"))
        if i in closed:
            db_session.add(InboundEvent(provider="pushover", event_key=pl.receipt_event_key(f"R{i}"),
                                        result="expired"))
    await db_session.commit()


async def test_open_receipts_behind_a_full_batch_of_closed_ones_are_polled(db_session, monkeypatch):
    batch = pl.BATCH
    # A full batch acknowledged in Klopot, another full batch closed (expired), then one open.
    await _receipts(db_session, 2 * batch + 1, acked=set(range(batch)), closed=set(range(batch, 2 * batch)))
    calls: list[str] = []

    async def status(config, receipt):
        calls.append(receipt)
        return {"status": 1, "acknowledged": 1, "acknowledged_by_device": "pixel"}

    monkeypatch.setattr(pl.pushover, "receipt_status", status)
    assert await pl.poll_receipts(db_session) == 1
    assert calls == [f"R{2 * batch}"]
