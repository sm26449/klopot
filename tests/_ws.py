"""A WebSocket client that drives an ASGI app in the test's own event loop.

Starlette's ``TestClient`` runs the app in a thread with an event loop of its
own, while the test's database engine belongs to the test's loop: a handler
that reads the database then uses its connections from a second loop, which
aiomysql refuses and aiosqlite (0.22+) hangs on. This speaks the ASGI
websocket protocol directly, in the one loop pytest-asyncio gives the test.

    async with ws_connect(app, "/v1/stream/state", headers={...}) as ws:
        hello = json.loads(await ws.receive_text())

A handshake the app closes instead of accepting raises ``WsClosed`` with the
close code, as a browser would see it.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

_TIMEOUT = 5.0


class WsClosed(Exception):
    def __init__(self, code: int, reason: str = "") -> None:
        super().__init__(f"closed {code} {reason}".strip())
        self.code = code
        self.reason = reason


class _Socket:
    def __init__(self, from_app: asyncio.Queue[dict[str, Any]]) -> None:
        self._from_app = from_app

    async def receive_text(self) -> str:
        msg = await asyncio.wait_for(self._from_app.get(), _TIMEOUT)
        if msg["type"] == "websocket.close":
            raise WsClosed(msg.get("code", 1000), msg.get("reason") or "")
        assert msg["type"] == "websocket.send", msg
        return str(msg["text"])


@contextlib.asynccontextmanager
async def ws_connect(app: Any, path: str, headers: dict[str, str] | None = None) -> AsyncIterator[_Socket]:
    route, _, query = path.partition("?")
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "path": route,
        "raw_path": route.encode(),
        "query_string": query.encode(),
        "headers": [(b"host", b"testserver"),
                    *((k.lower().encode(), v.encode()) for k, v in (headers or {}).items())],
        "subprotocols": [],
        "state": {},
    }
    to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    from_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    task = asyncio.create_task(app(scope, to_app.get, from_app.put))
    try:
        await to_app.put({"type": "websocket.connect"})
        first = await asyncio.wait_for(from_app.get(), _TIMEOUT)
        if first["type"] == "websocket.close":
            raise WsClosed(first.get("code", 1000), first.get("reason") or "")
        assert first["type"] == "websocket.accept", first
        yield _Socket(from_app)
        await to_app.put({"type": "websocket.disconnect", "code": 1000})
    finally:
        # A handler waiting on its own queue (not on the socket) notices a
        # disconnect only when it next sends; end it the way a server does.
        if not task.done():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 0.2)
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
