"""UI channel — broadcasts notifications to subscribed WebSocket clients.

The ``UIChannel`` itself is a thin wrapper around a process-local
``WSBroadcaster``. The WebSocket endpoint (``/v1/stream/notifications``)
registers connections with the broadcaster; the dispatcher routes
notifications to ``UIChannel.send()`` which calls
``WSBroadcaster.publish()``.

Slow-client protection: each connection has a bounded queue
(default 100). When full, oldest is dropped and the slow client is
flagged in logs. We never block the dispatcher waiting for a slow
WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from .base import BaseChannel, Notification, SendResult

logger = logging.getLogger(__name__)


@dataclass
class _Connection:
    ws: WebSocket
    queue: asyncio.Queue
    pump: asyncio.Task[None] | None = None
    dropped: int = 0


class WSBroadcaster:
    """One instance per process. The dispatcher publishes; the
    WebSocket endpoint registers/unregisters clients."""

    def __init__(self, *, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._connections: dict[int, _Connection] = {}
        self._counter = 0
        self._lock = asyncio.Lock()

    async def register(self, ws: WebSocket) -> int:
        """Add a connection. Returns an opaque handle for unregister."""
        async with self._lock:
            self._counter += 1
            handle = self._counter
            conn = _Connection(ws=ws, queue=asyncio.Queue(maxsize=self._queue_size))
            conn.pump = asyncio.create_task(self._pump(conn), name=f"ws-pump-{handle}")
            self._connections[handle] = conn
            logger.info("WS notifications: client %s connected (total=%d)",
                        handle, len(self._connections))
            return handle

    async def unregister(self, handle: int) -> None:
        async with self._lock:
            conn = self._connections.pop(handle, None)
        if conn and conn.pump:
            conn.pump.cancel()
            try:
                await conn.pump
            except (asyncio.CancelledError, Exception):
                pass

    async def publish(self, payload: dict[str, Any]) -> int:
        """Fan-out to all subscribers. Returns the number of clients
        that successfully enqueued (some may have dropped due to
        full queue)."""
        delivered = 0
        for conn in list(self._connections.values()):
            try:
                conn.queue.put_nowait(payload)
                delivered += 1
            except asyncio.QueueFull:
                # Drop oldest, enqueue new
                try:
                    conn.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    conn.queue.put_nowait(payload)
                    delivered += 1
                except asyncio.QueueFull:
                    pass
                conn.dropped += 1
        return delivered

    def stats(self) -> dict[str, Any]:
        return {
            "connections": len(self._connections),
            "total_dropped": sum(c.dropped for c in self._connections.values()),
        }

    async def _pump(self, conn: _Connection) -> None:
        """Per-connection drain loop."""
        try:
            while True:
                payload = await conn.queue.get()
                try:
                    await conn.ws.send_text(json.dumps(payload, default=str))
                except Exception:
                    return  # connection broken; the endpoint will unregister
        except asyncio.CancelledError:
            pass


# ── Module singleton ──────────────────────────────────────────────


_broadcaster: WSBroadcaster | None = None


def get_broadcaster() -> WSBroadcaster:
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = WSBroadcaster()
    return _broadcaster


# ── Channel adapter ───────────────────────────────────────────────


class UIChannel(BaseChannel):
    """Maps every routed notification to a WebSocket broadcast."""

    kind = "ui"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        broadcaster = get_broadcaster()
        payload = {
            "type": "notification",
            "id": notif.id,
            "notification_type": notif.type,
            "severity": notif.severity,
            "icon": notif.icon,
            "title": notif.title,
            "message": notif.message,
            "fired_at": notif.fired_at.isoformat() if hasattr(notif.fired_at, "isoformat") else str(notif.fired_at),
            "rule_id": notif.rule_id,
        }
        delivered = await broadcaster.publish(payload)
        # Always 'ok' — UI failures are silent (no-one listening is OK)
        return SendResult(ok=True, response={"clients_notified": delivered})

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "reachable": True,
            **get_broadcaster().stats(),
        }
