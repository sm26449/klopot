"""A transport error is stored by its kind, never with the request it quotes (review K08).

httpx's text for a protocol or URL error quotes what it was given: h11's
``Illegal header value b'Bearer <token> '`` carried the credential into
``deliveries.last_error``, ``delivery_attempts.error`` and the activity log
(``read`` scope). Connection, timeout and read/write errors keep their text
(an OS message the operator needs), as does any non-httpx exception; every
other httpx error keeps only its type.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.base import Notification
from app.channels.sms import SMSChannel
from app.channels.webhook import WebhookChannel
from app.core.activity import capture_exchanges
from app.utils import safe_http
from app.utils.redact import transport_error_text

pytestmark = pytest.mark.anyio

SECRET = "FAKE_TOKEN_K08_" + "x" * 12
_LEAKY = httpx.LocalProtocolError(f"Illegal header value b'Bearer {SECRET} '")


def test_transport_error_text():
    assert transport_error_text(_LEAKY) == "LocalProtocolError"
    assert transport_error_text(httpx.InvalidURL(f"bad https://h/{SECRET}")) == "InvalidURL"
    refused = httpx.ConnectError("[Errno 111] Connection refused")
    assert transport_error_text(refused) == "ConnectError: [Errno 111] Connection refused"
    assert transport_error_text(httpx.ReadTimeout("timed out")) == "ReadTimeout: timed out"
    assert transport_error_text(RuntimeError("boom")) == "RuntimeError: boom"


def _notif() -> Notification:
    return Notification(id="ntf_k08", type="t", severity="warning", icon=None, title="t", message="m",
                        fired_at=datetime(2026, 11, 15, 12, 0, 0))


async def _raise(*_a, **_kw):
    raise _LEAKY


@pytest.mark.parametrize(("adapter", "config"), [
    (WebhookChannel(), {"url": "https://hooks.example.com/x", "auth_kind": "bearer", "auth_value": "abc12345"}),
    (SMSChannel(), {"provider": "http", "url": "https://sms.example.com/send", "phone": "+40700000000"}),
])
async def test_adapters_store_only_the_error_kind(adapter, config):
    # Webhook sends through the shared helper (app/channels/_http.py).
    module = type(adapter).__module__
    target = "app.channels._http" if module == "app.channels.webhook" else module
    with patch(f"{target}.safe_request", new=_raise):
        result = await adapter.send(_notif(), config)
    assert result.ok is False
    assert SECRET not in (result.error or "")
    assert "LocalProtocolError" in (result.error or "")


async def test_the_activity_exchange_keeps_only_the_error_kind():
    class _Boom(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise _LEAKY

    with capture_exchanges() as exchanges, patch.object(safe_http, "screen_and_pick_ip",
                                                        new=AsyncMock(return_value="93.184.216.34")):
        async with httpx.AsyncClient(transport=_Boom()) as client:
            with pytest.raises(httpx.LocalProtocolError):
                await safe_http.safe_request("POST", "https://hooks.example.com/x", client=client, timeout=5.0)
    assert exchanges
    assert exchanges[0]["error"] == "LocalProtocolError"
