"""EmailChannel tests with mocked aiosmtplib."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiosmtplib
import pytest

from app.channels.base import Notification
from app.channels.email import EmailChannel, _render_html


def _notif(**overrides):
    defaults = dict(
        id="ntf_test", type="t", severity="warning", icon="⚠️",
        title="Battery Low", message="SOC at 18%",
        fired_at=datetime(2026, 5, 10, 12, 0, 0),
    )
    defaults.update(overrides)
    return Notification(**defaults)


@pytest.fixture
def channel():
    return EmailChannel()


@pytest.fixture(autouse=True)
def _allow_egress():
    # The SMTP-behaviour tests use an unresolvable placeholder host and mock
    # aiosmtplib; neutralize the egress pre-flight (S-09) so it doesn't reject
    # the placeholder. The egress screen itself is covered by test_egress_r06
    # and the dedicated S-09 tests below.
    with patch("app.channels.email.egress_blocked", return_value=None):
        yield


# ── Config validation ────────────────────────────────────────────


async def test_missing_smtp_host(channel):
    r = await channel.send(_notif(), {"from": "x", "to": ["y"]})
    assert r.ok is False
    assert "host" in r.error or "from" in r.error


async def test_missing_from(channel):
    r = await channel.send(_notif(), {"smtp_host": "h", "to": ["y"]})
    assert r.ok is False


async def test_missing_to(channel):
    r = await channel.send(_notif(), {"smtp_host": "h", "from": "x"})
    assert r.ok is False


# ── Successful send ──────────────────────────────────────────────


async def test_send_calls_aiosmtplib(channel):
    sent = AsyncMock()
    with patch("app.channels.email.aiosmtplib.send", sent):
        r = await channel.send(_notif(), {
            "smtp_host": "smtp.x", "smtp_port": 587,
            "from": "a@x", "to": ["b@x"],
            "username": "a@x", "password": "secret",
        })
    assert r.ok is True
    sent.assert_called_once()
    kwargs = sent.call_args.kwargs
    assert kwargs["hostname"] == "smtp.x"
    assert kwargs["port"] == 587
    assert kwargs["username"] == "a@x"
    assert kwargs["password"] == "secret"
    # STARTTLS for 587 default config
    assert kwargs["start_tls"] is True
    assert kwargs["use_tls"] is False


async def test_send_string_to_normalized_to_list(channel):
    """Single-recipient passed as a string should still work."""
    sent = AsyncMock()
    with patch("app.channels.email.aiosmtplib.send", sent):
        r = await channel.send(_notif(), {
            "smtp_host": "h", "from": "a", "to": "single@x",
        })
    assert r.ok is True
    assert "single@x" in r.response["to"]


async def test_implicit_ssl_when_ssl_true(channel):
    sent = AsyncMock()
    with patch("app.channels.email.aiosmtplib.send", sent):
        await channel.send(_notif(), {
            "smtp_host": "smtp.x", "smtp_port": 465,
            "from": "a", "to": ["b"], "ssl": True,
        })
    kwargs = sent.call_args.kwargs
    assert kwargs["use_tls"] is True   # implicit TLS (port 465)
    assert kwargs["start_tls"] is False


async def test_subject_prefix_per_severity(channel):
    sent = AsyncMock()
    captured: dict = {}

    async def capture(msg, **kw):
        captured["msg"] = msg

    with patch("app.channels.email.aiosmtplib.send", capture):
        await channel.send(
            _notif(severity="critical"),
            {"smtp_host": "h", "from": "a", "to": ["b"]},
        )
    assert captured["msg"]["Subject"].startswith("[CRIT]")


async def test_text_and_html_alternatives_present(channel):
    sent = AsyncMock()
    captured: dict = {}

    async def capture(msg, **kw):
        captured["msg"] = msg

    with patch("app.channels.email.aiosmtplib.send", capture):
        await channel.send(_notif(), {"smtp_host": "h", "from": "a", "to": ["b"]})

    msg = captured["msg"]
    # Walk parts
    parts = list(msg.walk())
    types = [p.get_content_type() for p in parts]
    assert "text/plain" in types
    assert "text/html" in types


# ── Failure paths ────────────────────────────────────────────────


async def test_smtp_exception_returns_error(channel):
    """SMTP-level error returns SendResult(ok=False) without raising."""
    err = aiosmtplib.errors.SMTPException("auth fail")
    with patch("app.channels.email.aiosmtplib.send", AsyncMock(side_effect=err)):
        r = await channel.send(_notif(), {
            "smtp_host": "h", "from": "a", "to": ["b"],
        })
    assert r.ok is False
    assert "SMTP" in r.error


async def test_network_error_caught(channel):
    with patch("app.channels.email.aiosmtplib.send", AsyncMock(side_effect=OSError("conn refused"))):
        r = await channel.send(_notif(), {
            "smtp_host": "h", "from": "a", "to": ["b"],
        })
    assert r.ok is False
    assert "network" in r.error


async def test_timeout_caught(channel):
    with patch("app.channels.email.aiosmtplib.send", AsyncMock(side_effect=TimeoutError())):
        r = await channel.send(_notif(), {
            "smtp_host": "h", "from": "a", "to": ["b"],
        })
    assert r.ok is False


# ── Healthcheck ──────────────────────────────────────────────────


async def test_healthcheck_no_host(channel):
    h = await channel.healthcheck({})
    assert h["reachable"] is False


async def test_healthcheck_tcp_probe_success(channel):
    """Simulate a successful TCP open_connection."""
    reader = MagicMock()
    writer = MagicMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    with patch(
        "asyncio.open_connection",
        AsyncMock(return_value=(reader, writer)),
    ):
        h = await channel.healthcheck({"smtp_host": "smtp.x", "smtp_port": 587})
    assert h["reachable"] is True
    assert h["host"] == "smtp.x"


async def test_healthcheck_tcp_probe_failure(channel):
    with patch(
        "asyncio.open_connection",
        AsyncMock(side_effect=ConnectionRefusedError("no")),
    ):
        h = await channel.healthcheck({"smtp_host": "smtp.x"})
    assert h["reachable"] is False


# ── HTML helper ──────────────────────────────────────────────────


def test_render_html_includes_title_and_message():
    html = _render_html(_notif(), "#FF0000")
    assert "Battery Low" in html
    assert "SOC at 18%" in html
    assert "#FF0000" in html


def test_render_html_no_message():
    html = _render_html(_notif(message=""), "#000")
    assert "Battery Low" in html


# ── A-12: untrusted notification text must not become email HTML ─────

def test_render_html_escapes_untrusted_fields():
    """Title/message/icon come from untrusted fire context, so markup in
    them must be rendered as text, never interpreted (audit A-12)."""
    out = _render_html(
        _notif(
            title='<script>alert(1)</script>',
            message='<img src=x onerror="steal()">&<b>bold</b>',
            icon='<svg/onload=1>',
        ),
        "#FF0000",
    )
    # The injected tags survive only in their escaped, inert form …
    assert "<script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "<img" not in out
    assert "onerror" in out  # present, but inside escaped text
    assert "&lt;img src=x onerror=&quot;steal()&quot;&gt;" in out
    assert "<svg/onload=1>" not in out
    assert "&lt;svg/onload=1&gt;" in out
    # … while the fixed decorative markup is untouched.
    assert "background:#FF0000" in out
    assert out.startswith("<!doctype html>")


def test_render_html_message_newlines_become_br_after_escaping():
    """Intended line breaks are preserved as <br>, but only after the
    content is escaped, so a crafted newline can't smuggle a real tag."""
    out = _render_html(_notif(message="line1\nline2\n<b>x"), "#000")
    assert "line1<br>line2<br>" in out
    assert "<b>x" not in out
    assert "&lt;b&gt;x" in out


def test_render_html_escapes_severity():
    out = _render_html(_notif(severity="<b>warn"), "#000")
    assert "<b>warn" not in out
    assert "&lt;b&gt;warn" in out


# ── F33: from_addr field, username fallback, comma recipient list ────

async def test_from_addr_field_is_accepted(channel):
    sent = AsyncMock()
    with patch("app.channels.email.aiosmtplib.send", sent):
        r = await channel.send(_notif(), {
            "smtp_host": "h", "from_addr": "sender@x", "to": ["b@x"],
        })
    assert r.ok is True
    assert sent.call_args.args[0]["From"] == "sender@x"


async def test_from_defaults_to_username(channel):
    sent = AsyncMock()
    with patch("app.channels.email.aiosmtplib.send", sent):
        r = await channel.send(_notif(), {
            "smtp_host": "h", "username": "user@x", "to": ["b@x"],
        })
    assert r.ok is True
    assert sent.call_args.args[0]["From"] == "user@x"


async def test_comma_separated_recipients_are_split(channel):
    sent = AsyncMock()
    with patch("app.channels.email.aiosmtplib.send", sent):
        r = await channel.send(_notif(), {
            "smtp_host": "h", "from_addr": "a@x", "to": "one@x, two@x ,three@x",
        })
    assert r.ok is True
    to_header = sent.call_args.args[0]["To"]
    assert "one@x" in to_header and "two@x" in to_header and "three@x" in to_header


# ── S-09: smtp_host must be egress-screened ────────────────────────────

from app.utils.egress import egress_blocked as _real_egress_blocked  # noqa: E402


async def test_blocks_metadata_smtp_host(channel):
    # Run the REAL egress screen (overriding the autouse neutralizer): a
    # metadata smtp_host must be refused before any connection (audit S-09).
    with patch("app.channels.email.egress_blocked", _real_egress_blocked):
        r = await channel.send(
            _notif(),
            {"smtp_host": "169.254.169.254", "from_addr": "a@example.com", "to": "b@example.com"},
        )
    assert r.ok is False
    assert "metadata" in r.error.lower()


async def test_healthcheck_blocks_metadata_smtp_host(channel):
    with patch("app.channels.email.egress_blocked", _real_egress_blocked):
        h = await channel.healthcheck({"smtp_host": "169.254.169.254"})
    assert h["reachable"] is False
    assert "metadata" in h["error"].lower()
