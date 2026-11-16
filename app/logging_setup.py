"""Logging setup for alertd.

Two formatters available:

- ``console`` (default) — human-friendly single-line: timestamp,
  level, logger, message. Used in dev.
- ``json`` — one JSON object per line for shipping to Loki / ELK.
  Includes timestamp, level, logger, message, plus any extra
  attributes attached via ``logger.info("...", extra={...})``.

Both formatters honor the trace_id contextvar set by
``request_trace_middleware`` so per-request log lines can be
correlated. The trace_id appears as ``trace_id`` in JSON or as
``[trace=…]`` prefix in console mode.

Switch via ``ALERTD_LOG_FORMAT=json|console``.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from typing import Any

from .config import get_settings

trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "alertd_trace_id", default=None,
)


_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


def _redact_output(text: str) -> str:
    """Redact credential-bearing URLs from a formatter's FINAL rendered line.

    The per-record filter only masks ``record.getMessage()``, but the formatters
    emit the exception traceback and the structured extras separately — so a
    token embedded in a raised exception's text (e.g. an httpx error carrying
    the full Telegram request URL) reached stdout verbatim (audit V11). Redacting
    the whole rendered line covers the message, the extras and the traceback
    alike. The mask (``<redacted>``) contains no JSON-special characters, so this
    can't corrupt a rendered JSON line."""
    from .utils.redact import redact_url

    try:
        return redact_url(text)
    except Exception:  # pragma: no cover — never break logging
        return text


class JsonFormatter(logging.Formatter):
    """One JSON line per record.

    ``logger.info("doing X", extra={"action": "fire", "type": "soc_low"})``
    becomes::

        {"ts":"2026-05-10T10:00:00Z","level":"INFO","logger":"app.x",
         "message":"doing X","action":"fire","type":"soc_low",
         "trace_id":"a1b2c3..."}
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace = trace_id_var.get()
        if trace:
            payload["trace_id"] = trace
        # Extra fields attached via logger.info(..., extra={...})
        for k, v in record.__dict__.items():
            if k in _RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps(v)
            except (TypeError, ValueError):
                v = repr(v)
            payload[k] = v
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return _redact_output(json.dumps(payload, default=str))


class ConsoleFormatter(logging.Formatter):
    """Human-readable, prepends a trace_id tag when the contextvar is set."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s %(name)s :: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)  # includes the exception traceback, if any
        trace = trace_id_var.get()
        out = f"[trace={trace[:8]}] {base}" if trace else base
        return _redact_output(out)


class _RedactingFilter(logging.Filter):
    """Mask credential-bearing URLs in every emitted record (audit R07).

    Rewrites the final rendered message so a leaked Telegram token / userinfo
    / secret query param can't reach stdout, even from third-party loggers
    (httpx logs the full request URL)."""

    def filter(self, record: logging.LogRecord) -> bool:
        from .utils.redact import redact_url

        try:
            msg = record.getMessage()
            redacted = redact_url(msg)
            if redacted != msg:
                record.msg = redacted
                record.args = ()
        except Exception:  # pragma: no cover — never break logging
            pass
        return True


class _AccessRedactingFilter(logging.Filter):
    """Redact credential-bearing URLs in access-log records (audit S-06).

    uvicorn's access logger emits the raw request line — including a WebSocket
    ``?api_key=`` query — through its own handler, which bypasses the root
    ``_RedactingFilter``. Its ``AccessFormatter`` unpacks ``record.args`` as a
    fixed 5-tuple, so the args are redacted IN PLACE (not collapsed into
    ``record.msg``, which would break that unpacking)."""

    def filter(self, record: logging.LogRecord) -> bool:
        from .utils.redact import redact_url

        try:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    redact_url(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: (redact_url(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            else:
                msg = record.getMessage()
                red = redact_url(msg)
                if red != msg:
                    record.msg, record.args = red, ()
        except Exception:  # pragma: no cover — never break logging
            pass
        return True


def configure_logging() -> None:
    """Replace the root handler with the right formatter for the env."""
    settings = get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())
    handler.addFilter(_RedactingFilter())
    root = logging.getLogger()
    # Drop pre-existing handlers (basicConfig may have run elsewhere)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(settings.log_level)
    # httpx/httpcore log the full request URL (which carries the Telegram bot
    # token) at INFO — keep them at WARNING so routine sends aren't logged
    # verbatim; the redacting filter is the backstop for anything they do emit.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # The access loggers have their OWN handlers (not the root one above), so a
    # `?api_key=` in a WebSocket request line would reach stdout unredacted
    # (audit S-06). uvicorn also logs the "WebSocket /…?api_key=… [accepted]"
    # line on uvicorn.error, so redact that logger too.
    access_filter = _AccessRedactingFilter()
    for access in ("uvicorn.access", "uvicorn.error", "gunicorn.access", "gunicorn.error"):
        logging.getLogger(access).addFilter(access_filter)


# ── Middleware: tag each request with a trace_id ─────────────────


# trace_id is persisted to VARCHAR(40) columns (notifications_log, audit_log),
# so an untrusted X-Trace-Id must be validated/bounded or a long value would
# fail the write with a 500 (audit F41).
_TRACE_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def accept_trace(incoming: str | None) -> str:
    """Use a well-formed, bounded incoming trace id; otherwise mint our own."""
    if incoming and _TRACE_RE.match(incoming):
        return incoming
    return uuid.uuid4().hex  # 32 chars, always within the column


async def request_trace_middleware(request, call_next):
    """ASGI middleware — sets the trace_id contextvar from the
    ``X-Trace-Id`` header when it is a safe, bounded token, else generates a
    UUID4. Echoes the effective trace id back to the caller so they can
    correlate."""
    trace = accept_trace(request.headers.get("x-trace-id"))
    # Also on the request: the 500 handler runs outside this middleware, after
    # the contextvar is reset, and must report the same id the logs carry.
    request.state.trace_id = trace
    token = trace_id_var.set(trace)
    try:
        response = await call_next(request)
    finally:
        trace_id_var.reset(token)
    response.headers["X-Trace-Id"] = trace
    return response


# Baseline hardening headers for every response, the 500 too (it is built
# outside the middleware stack). Permissions-Policy turns off browser
# features the admin UI never uses, for it and anything it might embed.
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}
