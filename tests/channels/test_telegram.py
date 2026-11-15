"""TelegramChannel tests with safe_request mocked (the channel goes through safe_http)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.base import Notification
from app.channels.telegram import TelegramChannel, _md_escape


def _notif(**overrides):
    defaults = dict(
        id="ntf_test",
        type="t",
        severity="warning",
        icon="⚠️",
        title="Battery Low",
        message="SOC at 18%",
        fired_at=datetime(2026, 5, 10, 12, 0, 0),
        vars_payload=None,
        rule_id=None,
    )
    defaults.update(overrides)
    return Notification(**defaults)


@pytest.fixture
def channel():
    return TelegramChannel()


def _mock_post(*, status: int = 200, body: dict | None = None):
    """Replace safe_request in the Telegram channel; returns (patcher, mock).
    The mock's call_args are (method, url) plus the keyword arguments."""
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body or {"ok": True, "result": {"message_id": 42}}
    response.text = "stub-text"
    response.content = b"{}"
    response.headers = {}
    mock = AsyncMock(return_value=response)
    return patch("app.channels.telegram.safe_request", mock), mock


# ── Config validation ─────────────────────────────────────────────


async def test_missing_bot_token_returns_error(channel):
    r = await channel.send(_notif(), {"chat_id": "123"})
    assert r.ok is False
    assert "bot_token" in r.error


async def test_missing_chat_id_returns_error(channel):
    r = await channel.send(_notif(), {"bot_token": "secret"})
    assert r.ok is False
    assert "chat_id" in r.error


# ── Successful send ───────────────────────────────────────────────


async def test_successful_send(channel):
    patcher, mock = _mock_post(status=200)
    with patcher:
        r = await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert r.ok is True
    assert r.response and r.response.get("message_id") == 42


async def test_send_uses_bot_api_url(channel):
    patcher, mock = _mock_post()
    with patcher:
        await channel.send(_notif(), {"bot_token": "BOTTOKEN", "chat_id": "123"})
    args, kwargs = mock.call_args
    assert args == ("POST", "https://api.telegram.org/botBOTTOKEN/sendMessage")


async def test_send_includes_severity_prefix(channel):
    patcher, mock = _mock_post()
    with patcher:
        await channel.send(
            _notif(severity="critical", title="Hot", message="Battery 60C"),
            {"bot_token": "tok", "chat_id": "123"},
        )
    body = mock.call_args.kwargs["json"]
    assert body["text"].startswith("🚨")
    assert "Hot" in body["text"]


async def test_send_default_parse_mode_markdown(channel):
    patcher, mock = _mock_post()
    with patcher:
        await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert mock.call_args.kwargs["json"]["parse_mode"] == "Markdown"


async def test_send_custom_parse_mode(channel):
    patcher, mock = _mock_post()
    with patcher:
        await channel.send(
            _notif(),
            {"bot_token": "tok", "chat_id": "123", "parse_mode": "HTML"},
        )
    assert mock.call_args.kwargs["json"]["parse_mode"] == "HTML"


async def test_html_message_escapes_template_values_and_keeps_ui_link_read_only(channel):
    patcher, mock = _mock_post()
    cfg = {"bot_token": "tok", "chat_id": "123", "parse_mode": "HTML",
           "inline_actions": True, "allowed_user_ids": [42], "actions_locale": "ro",
           "admin_url": "https://klopot.example/admin", "_notification_id": "ntf_test",
           "_action_keyboard": {"inline_keyboard": [[{"text": "Confirmă", "callback_data": "k:opaque"}]]}}
    with patcher:
        result = await channel.send(_notif(title="<script>", message="x & <b>y</b>"), cfg)
    body = mock.call_args.kwargs["json"]
    assert "&lt;script&gt;" in body["text"]
    assert "x &amp; &lt;b&gt;y&lt;/b&gt;" in body["text"]
    assert body["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "k:opaque"
    link = body["reply_markup"]["inline_keyboard"][-1][0]
    assert link == {"text": "Deschide în Klopot", "url": "https://klopot.example/admin/#/log?id=ntf_test"}
    assert result.response["view_url"] == link["url"]
    assert "tok" not in repr(result.response)


# ── Failure paths ─────────────────────────────────────────────────


async def test_4xx_returns_error(channel):
    patcher, _ = _mock_post(status=400, body={"ok": False, "description": "Bad Request"})
    with patcher:
        r = await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert r.ok is False
    assert "HTTP 400" in r.error


async def test_200_with_ok_false_returns_error(channel):
    """Bot API can return 200 with ``{"ok": false}`` on logical errors."""
    patcher, _ = _mock_post(status=200, body={"ok": False, "description": "chat not found"})
    with patcher:
        r = await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert r.ok is False


async def test_timeout_returns_error(channel):
    with patch("app.channels.telegram.safe_request", AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
        r = await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert r.ok is False
    assert "timeout" in r.error.lower()


async def test_http_error_caught(channel):
    with patch("app.channels.telegram.safe_request", AsyncMock(side_effect=httpx.HTTPError("boom"))):
        r = await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert r.ok is False
    assert "HTTPError" in r.error


# ── Healthcheck ───────────────────────────────────────────────────


async def test_healthcheck_no_token(channel):
    h = await channel.healthcheck({})
    assert h["reachable"] is False


async def test_healthcheck_ok(channel):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"ok": True, "result": {"username": "alertd_bot"}}
    with patch("app.channels.telegram.safe_request", AsyncMock(return_value=response)):
        h = await channel.healthcheck({"bot_token": "tok"})
    assert h["reachable"] is True
    assert h["bot_name"] == "alertd_bot"


# ── Markdown escape ───────────────────────────────────────────────


def test_md_escape_underscores():
    assert _md_escape("foo_bar") == "foo\\_bar"


def test_md_escape_asterisks():
    assert _md_escape("**bold**") == "\\*\\*bold\\*\\*"


def test_md_escape_backticks():
    assert _md_escape("code`bit`") == "code\\`bit\\`"


def test_md_escape_empty_string():
    assert _md_escape("") == ""


async def test_bot_api_server_is_a_setting_and_goes_through_safe_http(channel):
    """Pre-open-source audit: api.telegram.org was written out four times and
    called with a raw httpx client, bypassing the egress screening."""
    patcher, mock = _mock_post()
    cfg = {"bot_token": "T0K", "chat_id": "1", "api_url": "http://bot-api.local:8081/", "timeout_sec": 7}
    with patcher:
        await channel.send(_notif(), cfg)
        await channel.healthcheck(cfg)
    send, health = mock.call_args_list
    assert send.args == ("POST", "http://bot-api.local:8081/botT0K/sendMessage")
    assert send.kwargs["timeout"] == 7.0 and "block_private" in send.kwargs
    assert health.args == ("GET", "http://bot-api.local:8081/botT0K/getMe")


async def test_a_blocked_bot_api_server_is_an_error_without_the_token(channel):
    from app.utils.safe_http import EgressBlocked

    with patch("app.channels.telegram.safe_request", AsyncMock(side_effect=EgressBlocked("private address"))):
        r = await channel.send(_notif(), {"bot_token": "T0K", "chat_id": "1", "api_url": "http://10.0.0.5"})
    assert r.ok is False and r.error == "private address"
