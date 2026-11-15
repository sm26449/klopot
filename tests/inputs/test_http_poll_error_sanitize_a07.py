"""A-07: an input adapter's health ``error`` is surfaced by the
unauthenticated ``/v1/health`` and the read-scoped input health endpoint,
so it must never carry raw upstream text — neither a response body (which
can echo credentials) nor an exception string (which embeds the request
URL, with any token in it). Only stable categories are stored.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx

from app.inputs.http_poll import HTTPPollInput


async def _noop(topic, payload, source_kind):  # pragma: no cover - not called here
    ...


def _adapter() -> HTTPPollInput:
    return HTTPPollInput(name="t", config={"url": "https://up/x"}, on_value=_noop)


class _Resp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.text = text
        self.headers: dict[str, str] = {}


async def test_upstream_error_body_not_stored_in_health():
    a = _adapter()
    secret_body = '{"api_secret":"LEAK-abc123","detail":"upstream boom"}'
    # Patch the SSRF-safe seam (A-04): the adapter now delegates the request to
    # safe_request, which screens + pins the connection (tested separately).
    with patch(
        "app.inputs.http_poll.safe_request",
        AsyncMock(return_value=_Resp(503, secret_body)),
    ):
        await a._poll_once("https://up/x", "GET", {}, None, 5.0)
    err = a.health()["error"]
    assert err == "HTTP 503"            # a stable category, status only
    assert "LEAK-abc123" not in err     # the upstream body never surfaces
    assert a.health()["connected"] is False


async def test_connect_exception_url_not_stored_in_health():
    a = _adapter()
    # httpx exception messages routinely embed the full request URL, which
    # can carry userinfo / query credentials.
    exc = httpx.ConnectError("failed to connect to https://user:s3cret@up.internal/x")
    with patch("app.inputs.http_poll.safe_request", AsyncMock(side_effect=exc)):
        await a._poll_once("https://up/x", "GET", {}, None, 5.0)
    err = a.health()["error"]
    assert err == "ConnectError"        # exception class only, no message
    assert "s3cret" not in err
    assert "up.internal" not in err
