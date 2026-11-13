"""TelegramChannel tests with a mocked httpx.AsyncClient."""
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
    """Return a context manager that replaces httpx.AsyncClient with a
    mock whose .post() returns the desired response."""
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body or {"ok": True, "result": {"message_id": 42}}
    response.text = "stub-text"

    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)

    return patch("app.channels.telegram.httpx.AsyncClient", return_value=cm), client


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
    patcher, client = _mock_post(status=200)
    with patcher:
        r = await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert r.ok is True
    assert r.response and r.response.get("message_id") == 42


async def test_send_uses_bot_api_url(channel):
    patcher, client = _mock_post()
    with patcher:
        await channel.send(_notif(), {"bot_token": "BOTTOKEN", "chat_id": "123"})
    args, kwargs = client.post.call_args
    assert "BOTTOKEN/sendMessage" in args[0]


async def test_send_includes_severity_prefix(channel):
    patcher, client = _mock_post()
    with patcher:
        await channel.send(
            _notif(severity="critical", title="Hot", message="Battery 60C"),
            {"bot_token": "tok", "chat_id": "123"},
        )
    body = client.post.call_args.kwargs["json"]
    assert body["text"].startswith("🚨")
    assert "Hot" in body["text"]


async def test_send_default_parse_mode_markdown(channel):
    patcher, client = _mock_post()
    with patcher:
        await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert client.post.call_args.kwargs["json"]["parse_mode"] == "Markdown"


async def test_send_custom_parse_mode(channel):
    patcher, client = _mock_post()
    with patcher:
        await channel.send(
            _notif(),
            {"bot_token": "tok", "chat_id": "123", "parse_mode": "HTML"},
        )
    assert client.post.call_args.kwargs["json"]["parse_mode"] == "HTML"


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
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("app.channels.telegram.httpx.AsyncClient", return_value=cm):
        r = await channel.send(_notif(), {"bot_token": "tok", "chat_id": "123"})
    assert r.ok is False
    assert "timeout" in r.error.lower()


async def test_http_error_caught(channel):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=httpx.HTTPError("boom"))
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("app.channels.telegram.httpx.AsyncClient", return_value=cm):
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
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("app.channels.telegram.httpx.AsyncClient", return_value=cm):
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
