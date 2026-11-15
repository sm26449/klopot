"""ASGI request-body size limit (audit A-08).

A single process buffers an inbound body before any handler can apply a useful
cap (``await request.body()``, JSON/YAML parse), so an oversized POST can
exhaust memory. This middleware enforces a byte budget *before* the application
reads the body:

- **Content-Length fast-reject.** An honestly-declared oversized body is refused
  with ``413`` without reading it.
- **Streamed cap.** For chunked / undeclared bodies the middleware reads at most
  ``max_bytes`` (+1 to detect overflow); beyond that it refuses with ``413``.
  Otherwise it replays the buffered body to the app unchanged.

It is a pure ASGI middleware (not ``BaseHTTPMiddleware``) so the reject does not
pass through the app's catch-all exception handler, and buffering is bounded by
``max_bytes`` — which is the whole point. Bodyless methods pass straight through.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODYLESS = frozenset({"GET", "HEAD", "DELETE", "OPTIONS", "TRACE"})


class BodySizeLimitMiddleware:
    """Refuse an HTTP request whose body exceeds ``max_bytes`` with 413."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "").upper() in _BODYLESS:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        cl = headers.get(b"content-length")
        if cl is not None:
            try:
                if int(cl) > self.max_bytes:
                    await self._reject(scope, send)
                    return
            except ValueError:
                pass  # malformed Content-Length — fall through to streamed cap

        # Buffer up to the cap (+1 byte to detect overflow). Bounded by design.
        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                # Client went away before the app ran; nothing to serve.
                return
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > self.max_bytes:
                await self._reject(scope, send)
                return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            # Subsequent reads (e.g. disconnect) come from the real transport.
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        body = (
            b'{"error":{"code":"REQUEST_TOO_LARGE",'
            b'"message":"Request body exceeds the configured limit."}}'
        )
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
