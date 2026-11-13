"""SMSChannel tests. The channel sends through safe_request (SSRF-safe,
IP-pinned transport — audit S-05), so these mock safe_request, not httpx."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.channels.base import Notification
from app.channels.sms import _MAX_SMS_CHARS, SMSChannel
from app.utils.safe_http import EgressBlocked


def _notif(title="t", message="m"):
    return Notification(
        id="ntf_test",
        type="t",
        severity="warning",
        icon=None,
        title=title,
        message=message,
        fired_at=datetime(2026, 5, 10, 12, 0, 0),
    )


def _resp(*, status: int = 200, body: dict | None = None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body if body is not None else {"sent": True}
    r.text = "stub"
    return r


def _patch_send(*, status: int = 200, body: dict | None = None):
    """Patch safe_request to return a stub response; returns (patcher, mock)."""
    mock = AsyncMock(return_value=_resp(status=status, body=body))
    return patch("app.channels.sms.safe_request", mock), mock


async def test_missing_gateway_url():
    r = await SMSChannel().send(_notif(), {"phone": "+40700"})
    assert r.ok is False and "gateway_url" in r.error


async def test_missing_phone():
    r = await SMSChannel().send(_notif(), {"gateway_url": "http://gw"})
    assert r.ok is False and "phone" in r.error


async def test_successful_send():
    patcher, mock = _patch_send(status=200)
    with patcher:
        r = await SMSChannel().send(
            _notif(title="Battery Low", message="SOC 18%"),
            {"gateway_url": "http://gw", "phone": "+40700"},
        )
    assert r.ok is True
    assert mock.call_args.args[0] == "POST"
    body = mock.call_args.kwargs["json"]
    assert body["phone"] == "+40700"
    assert "Battery Low" in body["message"] and "SOC 18%" in body["message"]


async def test_uses_send_endpoint_path():
    patcher, mock = _patch_send()
    with patcher:
        await SMSChannel().send(
            _notif(), {"gateway_url": "http://gw/", "phone": "+40700"},
        )
    assert mock.call_args.args[1].endswith("/api/sms/send")


async def test_truncates_long_messages():
    patcher, mock = _patch_send()
    with patcher:
        await SMSChannel().send(
            _notif(message="x" * 1000),
            {"gateway_url": "http://gw", "phone": "+40700"},
        )
    body = mock.call_args.kwargs["json"]
    assert len(body["message"]) <= _MAX_SMS_CHARS
    assert body["message"].endswith("…")


async def test_api_key_attached_when_configured():
    patcher, mock = _patch_send()
    with patcher:
        await SMSChannel().send(
            _notif(),
            {"gateway_url": "http://gw", "phone": "+40700", "gateway_api_key": "secret"},
        )
    headers = mock.call_args.kwargs["headers"]
    assert headers.get("X-API-Key") == "secret"


async def test_4xx_returns_error():
    patcher, _ = _patch_send(status=503)
    with patcher:
        r = await SMSChannel().send(
            _notif(), {"gateway_url": "http://gw", "phone": "+40700"},
        )
    assert r.ok is False and "503" in r.error


async def test_timeout_returns_error():
    mock = AsyncMock(side_effect=httpx.TimeoutException("late"))
    with patch("app.channels.sms.safe_request", mock):
        r = await SMSChannel().send(
            _notif(), {"gateway_url": "http://gw", "phone": "+40700"},
        )
    assert r.ok is False and "timeout" in r.error.lower()


async def test_blocked_egress_returns_error():
    # SSRF: a gateway_url that fails the egress policy must fail the send, not
    # connect (audit S-05).
    mock = AsyncMock(side_effect=EgressBlocked("private address blocked"))
    with patch("app.channels.sms.safe_request", mock):
        r = await SMSChannel().send(
            _notif(), {"gateway_url": "http://169.254.169.254", "phone": "+40700"},
        )
    assert r.ok is False and "blocked" in r.error.lower()


async def test_healthcheck_reaches_health_endpoint():
    patcher, mock = _patch_send(status=200)
    with patcher:
        h = await SMSChannel().healthcheck({"gateway_url": "http://gw"})
    assert h["reachable"] is True
    assert mock.call_args.args[0] == "GET"
    assert mock.call_args.args[1].endswith("/api/health")


async def test_healthcheck_no_url():
    h = await SMSChannel().healthcheck({})
    assert h["reachable"] is False
