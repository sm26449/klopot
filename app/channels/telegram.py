"""Telegram channel — POST to Bot API ``sendMessage`` endpoint.

Config shape (stored in ``channels.config`` JSON):

    {
      "bot_token_ref": "TELEGRAM_BOT_TOKEN",  // env var name
      "chat_id": "123456789",
      "parse_mode": "Markdown"  // optional, default "Markdown"
    }

For dev convenience, ``bot_token`` literal is also accepted but
stored as plaintext; production should always use ``_ref``.
"""
from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

import httpx

from ..config import get_settings
from ..core.activity import note_exchange
from ..utils.redact import redact_url, transport_error_text
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from ..utils.telegram_api import api_url
from ._secrets import resolve_secret
from .base import HEALTHCHECK_TIMEOUT_SEC, BaseChannel, Notification, SendResult
from .telegram_config import action_labels, bot_key, public_view_url

logger = logging.getLogger(__name__)


_SEVERITY_PREFIX = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
}


class TelegramChannel(BaseChannel):
    """POST to the Telegram Bot API (``api_url``, default api.telegram.org —
    a self-hosted Bot API server works too), through safe_http."""

    kind = "telegram"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        token = resolve_secret(config, "bot_token", "bot_token_ref")
        chat_id = config.get("chat_id")
        if not token:
            return SendResult(ok=False, error="Missing bot_token (or bot_token_ref env var)")
        if not chat_id:
            return SendResult(ok=False, error="Missing chat_id")

        text = format_message(notif, config.get("parse_mode", "Markdown"))

        base = api_url(config)
        url = f"{base}/bot{token}/sendMessage"
        timeout = float(config.get("timeout_sec") or 10)
        body = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": config.get("parse_mode", "Markdown"),
            "disable_web_page_preview": True,
        }
        view_url = public_view_url(config, str(config.get("_notification_id") or notif.id), notif.incident_id)
        keyboard = config.get("_action_keyboard")
        if isinstance(keyboard, dict):
            rows = [list(row) for row in keyboard.get("inline_keyboard", [])]
            if view_url:
                rows.append([{"text": action_labels(config.get("actions_locale"))["view"], "url": view_url}])
            body["reply_markup"] = {"inline_keyboard": rows}
        # The bot token is in the URL path: the activity log gets a masked one.
        shown_url = f"{base}/bot<redacted>/sendMessage"
        started = time.monotonic()
        try:
            r = await safe_request("POST", url, json=body, timeout=timeout,
                                   block_private=get_settings().block_private_egress)
            note_exchange(method="POST", url=shown_url, url_is_masked=True, status=r.status_code,
                          duration_ms=int((time.monotonic() - started) * 1000), request_body=body,
                          response_body=r.content, response_headers=r.headers)
            if r.status_code == 200 and r.json().get("ok"):
                result = r.json()["result"]
                actual_chat = result.get("chat") or {}
                return SendResult(ok=True, response={
                    "provider": "telegram", "bot_key": bot_key(token),
                    "message_id": result.get("message_id"),
                    "chat_id": actual_chat.get("id", str(chat_id)), "view_url": view_url,
                })
            err = f"HTTP {r.status_code}: {r.text[:200]}"
            # Telegram's flood control: 429 with parameters.retry_after (seconds).
            retry_after = None
            if r.status_code == 429:
                try:
                    retry_after = float((r.json().get("parameters") or {}).get("retry_after") or 30)
                except (ValueError, TypeError, AttributeError):
                    retry_after = 30.0
            return SendResult(ok=False, error=redact_url(err), retry_after=retry_after,
                              permanent=r.status_code in (400, 401, 403, 404))
        except (EgressBlocked, ResponseTooLarge) as e:
            # The reason names the host only; the token is in the path.
            return SendResult(ok=False, error=e.reason)
        except httpx.TimeoutException:
            note_exchange(method="POST", url=shown_url, url_is_masked=True, status=None,
                          duration_ms=int((time.monotonic() - started) * 1000), request_body=body, error="timeout")
            return SendResult(ok=False, error="Telegram API timeout")
        except httpx.HTTPError as e:
            # httpx exception text includes the request URL — which carries
            # the bot token — so redact before returning/storing it (R07).
            note_exchange(method="POST", url=shown_url, url_is_masked=True, status=None,
                          duration_ms=int((time.monotonic() - started) * 1000), request_body=body,
                          error=type(e).__name__)
            return SendResult(ok=False, error=f"HTTP error: {transport_error_text(e)}")

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        token = resolve_secret(config, "bot_token", "bot_token_ref")
        if not token:
            return {"reachable": False, "error": "no token configured"}
        url = f"{api_url(config)}/bot{token}/getMe"
        try:
            r = await safe_request("GET", url, timeout=HEALTHCHECK_TIMEOUT_SEC,
                                   block_private=get_settings().block_private_egress)
            return {
                "reachable": r.status_code == 200,
                "status": r.status_code,
                "bot_name": r.json().get("result", {}).get("username") if r.status_code == 200 else None,
            }
        except EgressBlocked as e:
            return {"reachable": False, "error": e.reason}
        except Exception as e:
            return {"reachable": False, "error": transport_error_text(e)[:200]}


def format_message(notif: Notification, mode: str) -> str:
    prefix = _SEVERITY_PREFIX.get(notif.severity, "")
    # Leave headroom for formatting while keeping Telegram's UTF-16 budget.
    title = _truncate(notif.title, 500)
    message = _truncate(notif.message, 3400)
    if mode == "HTML":
        return f"{prefix} <b>{html.escape(title)}</b>\n{html.escape(message)}".strip()
    if mode == "MarkdownV2":
        def escape(value: str) -> str:
            return re.sub(r"([_\*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", value)
        return f"{prefix} *{escape(title)}*\n{escape(message)}".strip()
    if mode == "Markdown":
        return f"{prefix} *{_md_escape(title)}*\n{_md_escape(message)}".strip()
    return f"{prefix} {title}\n{message}".strip()


def _truncate(value: str, units: int) -> str:
    encoded = value.encode("utf-16-le")
    if len(encoded) <= units * 2:
        return value
    return encoded[:(units - 1) * 2].decode("utf-16-le", errors="ignore") + "…"


def _md_escape(s: str) -> str:
    """Escape characters that mint syntactic Markdown-V1 structures.

    Telegram Markdown is permissive, but a few characters carry
    syntax we want to neutralise:
      - ``_`` and ``*`` open/close italic/bold; an unbalanced one
        causes the message to fail with HTTP 400.
      - `` ` `` opens code-span (same failure mode).
      - ``[`` opens a link — a template containing
        ``[click](evil)`` would render as an actual link in the
        rendered message. Operator-controlled templates make this
        low risk, but cheap to close (audit L-2).

    Backslash escape works for all four in Markdown-V1.
    """
    if not s:
        return ""
    return (
        s.replace("_", "\\_")
         .replace("*", "\\*")
         .replace("`", "\\`")
         .replace("[", "\\[")
    )
