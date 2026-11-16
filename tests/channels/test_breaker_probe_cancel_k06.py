"""A cancelled dispatch gives its half-open probe back (review K06).

The breaker admits ONE trial send when an open channel's window has passed.
The trial is released when the send settles — but the dispatcher wraps the
first attempt in ``asyncio.wait_for``, and a cancellation skipped the settle
path: ``probe_in_flight`` stayed True and every later send to the channel was
deferred as ``circuit_open`` until the process restarted.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from app.channels.base import Notification, SendResult
from app.channels.manager import ChannelManager, DispatchOutcome
from app.db.models import ChannelKind


def _notif(i: int) -> Notification:
    return Notification(id=f"ntf_{i}", type="t", severity="warning", icon=None,
                        title="t", message="m", fired_at=datetime(2026, 5, 10, 12, 0, 0))


async def _open_breaker(mgr: ChannelManager, name: str) -> None:
    mgr._breaker._open_sec = 0          # the open window has already passed
    for _ in range(mgr._breaker._threshold):
        await mgr._breaker.record_failure(name, "down")


async def test_a_cancelled_probe_is_released(db_session, make_channel):
    mgr = ChannelManager()
    db_session.add(make_channel(kind=ChannelKind.ui, name="slow_ch"))
    await db_session.commit()
    slow = {"on": True}

    async def send(notif, cfg, idempotency_key=None):
        if slow["on"]:
            await asyncio.sleep(5)
        return SendResult(ok=True)

    adapter = type("Adapter", (), {"send": staticmethod(send)})()
    await _open_breaker(mgr, "slow_ch")
    with patch.object(mgr, "_get_adapter", return_value=adapter):
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(mgr.dispatch(_notif(1), ["slow_ch"], db_session, outcome=DispatchOutcome()),
                                   timeout=0.1)
        assert mgr._breaker.state("slow_ch").probe_in_flight is False
        slow["on"] = False
        later = await mgr.dispatch(_notif(2), ["slow_ch"], db_session)
    assert later.succeeded == ["slow_ch"]
    assert mgr._breaker.state("slow_ch").state == "closed"


async def test_a_probe_cancelled_before_its_send_started_is_released(db_session, make_channel):
    """Cancelled while another channel is still being admitted: the probe of a
    channel admitted earlier must not leak either."""
    mgr = ChannelManager()
    db_session.add_all([make_channel(kind=ChannelKind.ui, name="probe_ch"),
                        make_channel(kind=ChannelKind.ui, name="busy_ch")])
    await db_session.commit()
    await _open_breaker(mgr, "probe_ch")
    real_allow = mgr._limiter.allow

    async def slow_limiter(name, per_min):
        if name == "busy_ch":
            await asyncio.sleep(5)
        return await real_allow(name, per_min)

    async def send(notif, cfg, idempotency_key=None):
        return SendResult(ok=True)

    adapter = type("Adapter", (), {"send": staticmethod(send)})()
    with patch.object(mgr, "_get_adapter", return_value=adapter), \
            patch.object(mgr._limiter, "allow", side_effect=slow_limiter):
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(mgr.dispatch(_notif(3), ["probe_ch", "busy_ch"], db_session), timeout=0.1)
    assert mgr._breaker.state("probe_ch").probe_in_flight is False
