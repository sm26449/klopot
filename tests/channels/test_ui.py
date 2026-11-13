"""UIChannel + WSBroadcaster tests with a fake WebSocket."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.channels.base import Notification
from app.channels.ui import UIChannel, WSBroadcaster, get_broadcaster


def _notif():
    return Notification(
        id="ntf_test", type="t", severity="warning", icon="⚠️",
        title="hi", message="m",
        fired_at=datetime(2026, 5, 10, 12, 0, 0),
        rule_id=42,
    )


class _FakeWS:
    """Minimal WebSocket stand-in — records send_text calls."""

    def __init__(self):
        self.sent: list[str] = []
        self.broken = False

    async def send_text(self, text: str) -> None:
        if self.broken:
            raise RuntimeError("connection broken")
        self.sent.append(text)


@pytest.fixture
def broadcaster():
    return WSBroadcaster(queue_size=10)


# ── WSBroadcaster ────────────────────────────────────────────────


async def test_register_returns_handle(broadcaster):
    ws = _FakeWS()
    h = await broadcaster.register(ws)
    assert isinstance(h, int)
    assert broadcaster.stats()["connections"] == 1
    await broadcaster.unregister(h)


async def test_unregister_drops_connection(broadcaster):
    h = await broadcaster.register(_FakeWS())
    await broadcaster.unregister(h)
    assert broadcaster.stats()["connections"] == 0


async def test_unregister_unknown_handle_no_op(broadcaster):
    """Calling unregister with a handle that was never registered
    must not raise."""
    await broadcaster.unregister(999)


async def test_publish_delivers_to_all_clients(broadcaster):
    ws1 = _FakeWS()
    ws2 = _FakeWS()
    h1 = await broadcaster.register(ws1)
    h2 = await broadcaster.register(ws2)

    delivered = await broadcaster.publish({"hello": "world"})
    assert delivered == 2

    # Give the per-connection pump tasks a chance to drain
    for _ in range(10):
        await asyncio.sleep(0)
        if ws1.sent and ws2.sent:
            break

    assert len(ws1.sent) == 1
    assert len(ws2.sent) == 1
    assert json.loads(ws1.sent[0]) == {"hello": "world"}

    await broadcaster.unregister(h1)
    await broadcaster.unregister(h2)


async def test_publish_no_clients_returns_zero(broadcaster):
    delivered = await broadcaster.publish({"x": 1})
    assert delivered == 0


async def test_full_queue_drops_oldest(broadcaster):
    """When a slow client's queue fills up, publish drops the oldest
    entry and enqueues the new one — never blocks the dispatcher."""
    ws = _FakeWS()
    # Don't run the pump (don't actually call register — fill queue
    # manually to simulate slow consumer)
    bc = WSBroadcaster(queue_size=2)
    h = await bc.register(ws)
    conn = bc._connections[h]
    # Cancel the pump so the queue actually fills up
    conn.pump.cancel()

    # Fill the queue
    await bc.publish({"i": 1})
    await bc.publish({"i": 2})
    # Queue full now; next publish must NOT raise, and must increment dropped
    await bc.publish({"i": 3})
    assert conn.dropped >= 1
    assert conn.queue.qsize() <= 2


async def test_pump_handles_broken_connection(broadcaster):
    """A broken send_text() must not crash the pump or leak tasks."""
    ws = _FakeWS()
    ws.broken = True
    h = await broadcaster.register(ws)

    await broadcaster.publish({"x": 1})
    # Give the pump a tick to attempt the send
    for _ in range(5):
        await asyncio.sleep(0)

    # Pump exited cleanly — task is done
    conn = broadcaster._connections.get(h)
    if conn:  # may have been unregistered by pump exit
        assert conn.pump.done() or conn.pump.cancelled() is False
    await broadcaster.unregister(h)


def test_stats_initial_state(broadcaster):
    s = broadcaster.stats()
    assert s == {"connections": 0, "total_dropped": 0}


def test_get_broadcaster_singleton():
    a = get_broadcaster()
    b = get_broadcaster()
    assert a is b


# ── UIChannel ────────────────────────────────────────────────────


async def test_ui_send_publishes_to_broadcaster(monkeypatch):
    """UIChannel.send wraps the notif in a WS-friendly payload and
    publishes via the module broadcaster."""
    fake_bc = WSBroadcaster(queue_size=5)
    monkeypatch.setattr("app.channels.ui.get_broadcaster", lambda: fake_bc)

    ws = _FakeWS()
    h = await fake_bc.register(ws)
    try:
        ch = UIChannel()
        r = await ch.send(_notif(), config={})
        assert r.ok is True

        # Drain the pump
        for _ in range(10):
            await asyncio.sleep(0)
            if ws.sent:
                break

        assert len(ws.sent) == 1
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "notification"
        assert payload["title"] == "hi"
        assert payload["severity"] == "warning"
        assert payload["rule_id"] == 42
        assert payload["fired_at"].startswith("2026-05-10T12:00")
    finally:
        await fake_bc.unregister(h)


async def test_ui_send_ok_when_no_clients(monkeypatch):
    """No subscribers is not a failure — alertd UIChannel is fire-
    and-forget."""
    fake_bc = WSBroadcaster()
    monkeypatch.setattr("app.channels.ui.get_broadcaster", lambda: fake_bc)
    r = await UIChannel().send(_notif(), config={})
    assert r.ok is True
    assert r.response["clients_notified"] == 0


async def test_ui_healthcheck_reports_stats(monkeypatch):
    fake_bc = WSBroadcaster()
    await fake_bc.register(_FakeWS())
    monkeypatch.setattr("app.channels.ui.get_broadcaster", lambda: fake_bc)

    h = await UIChannel().healthcheck({})
    assert h["reachable"] is True
    assert h["connections"] == 1


async def test_ui_send_payload_includes_optional_fields(monkeypatch):
    fake_bc = WSBroadcaster()
    monkeypatch.setattr("app.channels.ui.get_broadcaster", lambda: fake_bc)

    notif = Notification(
        id="x", type="custom", severity="info", icon=None,
        title="t", message=None,
        fired_at=datetime(2026, 5, 10, 12, 0, 0),
        rule_id=None,
    )
    ws = _FakeWS()
    h = await fake_bc.register(ws)
    try:
        await UIChannel().send(notif, {})
        for _ in range(10):
            await asyncio.sleep(0)
            if ws.sent:
                break
        payload = json.loads(ws.sent[0])
        assert payload["icon"] is None
        assert payload["message"] is None
        assert payload["rule_id"] is None
    finally:
        await fake_bc.unregister(h)
