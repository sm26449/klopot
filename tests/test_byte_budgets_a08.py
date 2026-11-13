"""A-08: byte budgets for inbound bodies, config YAML, and upstream responses.

- The ASGI body-limit middleware refuses an oversized request before any
  handler buffers it (Content-Length fast-reject and streamed cap).
- Config YAML loading rejects aliases (billion-laughs) and over-deep nesting.
- ``safe_request`` caps the decompressed response body.
"""
from __future__ import annotations

import httpx
import pytest

from app.body_limit import BodySizeLimitMiddleware
from app.utils.safe_http import ResponseTooLarge, safe_request
from app.utils.safe_yaml import BoundedYAMLError, load_bounded

pytestmark = pytest.mark.anyio


# ── ASGI body-limit middleware ───────────────────────────────────────


class _InnerApp:
    """Records whether it ran and the full body it received."""

    def __init__(self) -> None:
        self.ran = False
        self.body: bytes | None = None

    async def __call__(self, scope, receive, send):
        self.ran = True
        body = bytearray()
        more = True
        while more:
            m = await receive()
            body += m.get("body", b"")
            more = m.get("more_body", False)
        self.body = bytes(body)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _drive(mw, *, method="POST", chunks=None, content_length=None):
    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    scope = {"type": "http", "method": method, "headers": headers}
    queue = list(chunks or [(b"", False)])

    async def receive():
        if queue:
            body, more = queue.pop(0)
            return {"type": "http.request", "body": body, "more_body": more}
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(m):
        sent.append(m)

    await mw(scope, receive, send)
    return sent


def _status(sent):
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


async def test_content_length_over_cap_rejected_without_reading():
    inner = _InnerApp()
    mw = BodySizeLimitMiddleware(inner, max_bytes=10)
    sent = await _drive(mw, content_length=1000)
    assert _status(sent) == 413
    assert inner.ran is False     # never reached the app


async def test_streamed_body_over_cap_rejected():
    inner = _InnerApp()
    mw = BodySizeLimitMiddleware(inner, max_bytes=10)
    # No Content-Length; stream 6 + 6 = 12 bytes > 10.
    sent = await _drive(mw, chunks=[(b"aaaaaa", True), (b"bbbbbb", False)])
    assert _status(sent) == 413
    assert inner.ran is False


async def test_body_under_cap_passes_through_intact():
    inner = _InnerApp()
    mw = BodySizeLimitMiddleware(inner, max_bytes=100)
    sent = await _drive(mw, chunks=[(b"hello ", True), (b"world", False)], content_length=11)
    assert _status(sent) == 200
    assert inner.ran is True
    assert inner.body == b"hello world"   # replayed unchanged


async def test_bodyless_get_passes_through():
    inner = _InnerApp()
    mw = BodySizeLimitMiddleware(inner, max_bytes=1)
    sent = await _drive(mw, method="GET")
    assert _status(sent) == 200
    assert inner.ran is True


# ── Bounded YAML ─────────────────────────────────────────────────────


def test_yaml_aliases_are_rejected():
    # The "billion laughs" shape: anchors + aliases expanding exponentially.
    bomb = (
        "a: &a [x, x]\n"
        "b: &b [*a, *a]\n"
        "c: [*b, *b]\n"
    )
    with pytest.raises(BoundedYAMLError):
        load_bounded(bomb, max_depth=50)


def test_yaml_depth_cap_enforced():
    deep = "v: " + "[" * 60 + "]" * 60
    with pytest.raises(BoundedYAMLError):
        load_bounded(deep, max_depth=20)


def test_normal_yaml_loads():
    data = load_bounded("rules:\n  - name: a\n    x: 1\nmeta: {k: v}\n", max_depth=50)
    assert data["rules"][0]["name"] == "a"
    assert data["meta"]["k"] == "v"


def test_yaml_parse_error_is_wrapped():
    with pytest.raises(BoundedYAMLError):
        load_bounded("a: [1, 2\n", max_depth=50)   # unbalanced


# ── Response byte cap ────────────────────────────────────────────────


def _mock_client(body: bytes):
    def handler(request):
        return httpx.Response(200, content=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_response_over_cap_raises():
    client = _mock_client(b"x" * 5000)
    async with client:
        with pytest.raises(ResponseTooLarge):
            await safe_request(
                "GET", "https://h/x", timeout=5, resolver=lambda h: ["93.184.216.34"],
                max_response_bytes=1000, client=client,
            )


async def test_response_under_cap_is_returned_and_usable():
    client = _mock_client(b"hello")
    async with client:
        r = await safe_request(
            "GET", "https://h/x", timeout=5, resolver=lambda h: ["93.184.216.34"],
            max_response_bytes=1000, client=client,
        )
    assert r.status_code == 200
    assert r.text == "hello"      # body readable after capped streaming


# ── Wiring: the middleware is actually installed on the app ───────────


async def test_oversized_request_rejected_end_to_end(db_client, admin_key):
    from app.config import get_settings

    oversized = b"a" * (get_settings().max_request_bytes + 1024)
    r = await db_client.post(
        "/v1/config/validate",
        content=oversized,
        headers={"X-API-Key": admin_key, "Content-Type": "application/yaml"},
    )
    assert r.status_code == 413
