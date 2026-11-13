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

import logging
from typing import Any

import httpx

from ..utils.redact import redact_url
from ._secrets import resolve_secret
from .base import BaseChannel, Notification, SendResult

logger = logging.getLogger(__name__)


_SEVERITY_PREFIX = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
}


class TelegramChannel(BaseChannel):
    """Async POST to api.telegram.org Bot API."""

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

        prefix = _SEVERITY_PREFIX.get(notif.severity, "")
        text = f"{prefix} *{_md_escape(notif.title)}*\n{_md_escape(notif.message)}".strip()

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": config.get("parse_mode", "Markdown"),
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, json=body)
            if r.status_code == 200 and r.json().get("ok"):
                return SendResult(ok=True, response={"message_id": r.json()["result"].get("message_id")})
            err = f"HTTP {r.status_code}: {r.text[:200]}"
            return SendResult(ok=False, error=redact_url(err))
        except httpx.TimeoutException:
            return SendResult(ok=False, error="Telegram API timeout")
        except httpx.HTTPError as e:
            # httpx exception text includes the request URL — which carries
            # the bot token — so redact before returning/storing it (R07).
            return SendResult(ok=False, error=redact_url(f"HTTP error: {type(e).__name__}: {e}"))

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        token = resolve_secret(config, "bot_token", "bot_token_ref")
        if not token:
            return {"reachable": False, "error": "no token configured"}
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url)
            return {
                "reachable": r.status_code == 200,
                "status": r.status_code,
                "bot_name": r.json().get("result", {}).get("username") if r.status_code == 200 else None,
            }
        except Exception as e:
            return {"reachable": False, "error": redact_url(str(e))[:200]}


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
