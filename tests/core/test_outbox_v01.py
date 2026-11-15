"""V01: a retry must deliver to the destination frozen at enqueue time.

F03 froze only the per-route ``channel_overrides`` delta on the delivery;
the channel's *base* config was still read live on every attempt. So an
admin editing the channel's base destination (URL / chat / phone / token)
between the first attempt and a retry caused the retry to target the NEW
destination — a misdelivery / disclosure risk. The fix freezes the full
effective config on the delivery so every attempt uses the same identity.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import select

from app.channels.base import SendResult
from app.channels.manager import ChannelManager
from app.core.delivery_worker import DeliveryWorker
from app.core.dispatcher import FireEnvelope, fire
from app.db.models import (
    ChannelKind,
    Delivery,
    DeliveryState,
    Severity,
    TemplateChannel,
)
from app.utils.time import utc_now


class _CapturingAdapter:
    """Records the effective config each ``send`` receives; fails the first
    (retryable) attempt, then succeeds."""

    def __init__(self) -> None:
        self.configs: list[dict] = []

    async def send(self, notif, config, *, idempotency_key=None):
        self.configs.append(dict(config))
        if len(self.configs) == 1:
            return SendResult(ok=False, error="timeout")
        return SendResult(ok=True)

    async def healthcheck(self, config):
        return {"ok": True}


async def test_retry_still_uses_changed_base_destination(
    db_session, make_template, make_channel
):
    t = make_template(min_repeat_min=0)
    c = make_channel(
        kind=ChannelKind.webhook,
        config={"url": "https://fake.invalid/original", "token": "T1"},
    )
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c.id, severity_min=Severity.info, enabled=True,
    ))
    await db_session.commit()

    adapter = _CapturingAdapter()
    with patch.object(ChannelManager, "_get_adapter", return_value=adapter):
        r = await fire(FireEnvelope(type=t.type, context={"k": 1}), db_session)
        await db_session.commit()

        # Sync first attempt saw the original destination and failed → pending.
        assert adapter.configs[0]["url"] == "https://fake.invalid/original"
        d = (await db_session.execute(
            select(Delivery).where(Delivery.notification_id == r.id)
        )).scalar_one()
        assert d.state == DeliveryState.pending

        # Admin edits the channel's BASE destination between attempts.
        c.config = {"url": "https://fake.invalid/changed", "token": "T1"}
        d.next_attempt_at = utc_now() - timedelta(seconds=1)
        d.lease_until = None
        await db_session.commit()

        # The retry must still target the destination frozen at enqueue.
        await DeliveryWorker()._process_due(db_session)

    assert len(adapter.configs) == 2, adapter.configs
    assert adapter.configs[1]["url"] == "https://fake.invalid/original", (
        "retry delivered to the edited base destination — the enqueue-time "
        "destination was not frozen (F03 only froze the override delta)"
    )
