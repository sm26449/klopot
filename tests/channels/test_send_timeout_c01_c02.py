"""C-01 / C-02: a hung channel send must not stall the dispatcher or wedge the
breaker's half-open probe. Each send is bounded by adapter_send_timeout_sec; on
timeout the channel is recorded as failed and dispatch returns promptly."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from unittest.mock import patch

import pytest

from app.channels.base import Notification, SendResult
from app.channels.manager import ChannelManager
from app.config import get_settings
from app.db.models import ChannelKind


def _notif():
    return Notification(
        id="ntf_test", type="t", severity="warning", icon=None,
        title="t", message="m", fired_at=datetime(2026, 5, 10, 12, 0, 0),
    )


@pytest.fixture
async def manager():
    return ChannelManager()


@pytest.fixture
async def channel_row(db_session, make_channel):
    c = make_channel(kind=ChannelKind.ui, name="ui_slow")
    db_session.add(c)
    await db_session.commit()
    return c


async def test_hung_send_times_out_and_records_failure(manager, channel_row, db_session):
    fast = get_settings().model_copy(update={"adapter_send_timeout_sec": 0.05})

    async def _hang(*_a, **_k):
        await asyncio.sleep(5)
        return SendResult(ok=True)

    adapter = type("Slow", (), {"send": staticmethod(_hang)})()
    with patch.object(manager, "_get_adapter", return_value=adapter), \
         patch("app.channels.manager.get_settings", return_value=fast):
        start = time.perf_counter()
        out = await manager.dispatch(_notif(), [channel_row.name], db_session)
        elapsed = time.perf_counter() - start

    assert channel_row.name in out.failed
    assert "timed out" in out.failed[channel_row.name]
    # Returned in ~the timeout, not the 5 s the adapter would have slept.
    assert elapsed < 2.0


async def test_timeout_counts_as_a_breaker_failure(manager, channel_row, db_session):
    fast = get_settings().model_copy(update={"adapter_send_timeout_sec": 0.05})

    async def _hang(*_a, **_k):
        await asyncio.sleep(5)

    adapter = type("Slow", (), {"send": staticmethod(_hang)})()
    with patch.object(manager, "_get_adapter", return_value=adapter), \
         patch("app.channels.manager.get_settings", return_value=fast):
        await manager.dispatch(_notif(), [channel_row.name], db_session)

    # A timed-out probe records a failure, so the breaker state advances instead
    # of wedging until a restart (audit C-01).
    assert manager._breaker._state.get(channel_row.name) is not None
