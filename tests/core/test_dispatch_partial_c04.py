"""C-04: when the synchronous first attempt is cancelled on its overall budget,
channels that already succeeded must be recorded (in the shared outcome) so they
are NOT re-sent on retry. Previously the timeout path marked every channel failed."""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from app.channels.base import Notification, SendResult
from app.channels.manager import ChannelManager, DispatchOutcome
from app.db.models import ChannelKind


def _notif():
    return Notification(
        id="ntf_test", type="t", severity="warning", icon=None,
        title="t", message="m", fired_at=datetime(2026, 5, 10, 12, 0, 0),
    )


@pytest.fixture
async def manager():
    return ChannelManager()


async def test_cancelled_first_attempt_keeps_settled_channel(manager, db_session, make_channel):
    fast = make_channel(kind=ChannelKind.ui, name="fast_ch")
    slow = make_channel(kind=ChannelKind.ui, name="slow_ch")
    slow.config = {"_delay": 0.5}
    db_session.add_all([fast, slow])
    await db_session.commit()

    async def send(notif, cfg, idempotency_key=None):
        if cfg.get("_delay"):
            await asyncio.sleep(cfg["_delay"])
        return SendResult(ok=True)

    adapter = type("X", (), {"send": staticmethod(send)})()
    out = DispatchOutcome()
    with patch.object(manager, "_get_adapter", return_value=adapter):
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await asyncio.wait_for(
                manager.dispatch(_notif(), ["fast_ch", "slow_ch"], db_session, outcome=out),
                timeout=0.15,
            )

    # The fast channel settled before the cancel and is recorded; the slow one
    # was still in flight, so it is left for retry — not double-sent.
    assert "fast_ch" in out.succeeded
    assert "slow_ch" not in out.succeeded
