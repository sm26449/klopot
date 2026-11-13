"""R07: credential-bearing URLs must not leak into logs or stored errors."""
from __future__ import annotations

import json
import logging
import sys

from app.logging_setup import ConsoleFormatter, JsonFormatter, _RedactingFilter
from app.utils.redact import redact_url


def test_redacts_telegram_bot_token_in_path():
    url = "https://api.telegram.org/bot123456:AA-ZZ_secrettoken/sendMessage"
    out = redact_url(url)
    assert "secrettoken" not in out
    assert "/bot<redacted>" in out


def test_redacts_userinfo():
    out = redact_url("https://user:s3cret@hook.example/path")
    assert "s3cret" not in out
    assert "<redacted>@hook.example" in out


def test_redacts_secret_query_params():
    out = redact_url("https://h/x?token=abc123&foo=bar&api_key=zzz")
    assert "abc123" not in out
    assert "zzz" not in out
    assert "foo=bar" in out  # non-secret params preserved


def test_redacts_url_inside_exception_message():
    msg = "HTTP error: ConnectError: failed to connect to " \
          "https://api.telegram.org/bot999:TOP_SECRET/sendMessage"
    out = redact_url(msg)
    assert "TOP_SECRET" not in out


def test_non_strings_passthrough():
    assert redact_url(None) is None
    assert redact_url(123) == 123
    assert redact_url("") == ""


def test_logging_filter_masks_record_message():
    f = _RedactingFilter()
    rec = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1,
        "HTTP Request: POST https://api.telegram.org/bot42:LEAK/sendMessage",
        (), None,
    )
    assert f.filter(rec) is True
    assert "LEAK" not in rec.getMessage()


def _record_with_exc_url() -> logging.LogRecord:
    """A record with a BENIGN message but a secret riding in the exception —
    the shape of a ``logger.exception`` on a provider send failure (V11)."""
    try:
        raise RuntimeError(
            "send failed: POST "
            "https://api.telegram.org/bot42:TRACE_SECRET/sendMessage"
        )
    except RuntimeError:
        exc_info = sys.exc_info()
    return logging.LogRecord(
        "app.channels.manager", logging.ERROR, __file__, 1,
        "channel dispatch failed", (), exc_info,
    )


def test_logging_filter_leaves_credential_in_traceback():
    # V11: the message is benign; the token rides in the exception traceback,
    # which the message-only filter never touched. The JSON formatter emits the
    # traceback as a separate field, so the token reached stdout verbatim.
    out = JsonFormatter().format(_record_with_exc_url())
    assert "TRACE_SECRET" not in out
    assert "<redacted>" in out          # the traceback URL was masked
    json.loads(out)                     # mask is JSON-safe — still a valid line


def test_console_formatter_redacts_traceback_credential():
    out = ConsoleFormatter().format(_record_with_exc_url())
    assert "TRACE_SECRET" not in out
    assert "api.telegram.org/bot<redacted>" in out


def test_json_formatter_redacts_structured_extra_field():
    # A secret URL in a structured extra field (logger.info(..., extra=...))
    # was emitted raw by the JSON formatter too.
    rec = logging.LogRecord("app.x", logging.INFO, __file__, 1, "ok", (), None)
    rec.url = "https://api.telegram.org/bot7:EXTRA_SECRET/sendMessage"
    out = JsonFormatter().format(rec)
    assert "EXTRA_SECRET" not in out
    json.loads(out)
