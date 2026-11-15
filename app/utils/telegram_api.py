"""Bounded Bot API calls to Telegram (or a self-hosted Bot API server).

Every call goes through :mod:`app.utils.safe_http` (egress screening, IP
pinning, no redirects, a response cap), like any other outbound request.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import get_settings
from .safe_http import EgressBlocked, ResponseTooLarge, safe_request

DEFAULT_API_URL = "https://api.telegram.org"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def api_url(config: dict[str, Any] | None) -> str:
    """The Bot API origin of a channel config (``api_url``, default Telegram's)."""
    value = str((config or {}).get("api_url") or "").strip()
    return (value or DEFAULT_API_URL).rstrip("/")


class TelegramAPIError(Exception):
    def __init__(self, status: int | None, *, not_modified: bool = False) -> None:
        super().__init__(f"Telegram HTTP {status}" if status else "Telegram transport error")
        self.status = status
        self.not_modified = not_modified


async def call_bot(
    token: str, method: str, payload: dict[str, Any], *,
    base_url: str = DEFAULT_API_URL, io_timeout: float = 10,
) -> Any:
    if method not in {"getUpdates", "getMe", "answerCallbackQuery", "editMessageReplyMarkup"}:
        raise ValueError("unsupported Bot API method")
    try:
        response = await safe_request(
            "POST", f"{base_url.rstrip('/')}/bot{token}/{method}", json=payload, timeout=io_timeout,
            block_private=get_settings().block_private_egress, max_response_bytes=_MAX_RESPONSE_BYTES,
        )
    except (httpx.HTTPError, EgressBlocked, ResponseTooLarge):
        # Exception URLs can contain the bot token. Do not retain the cause.
        raise TelegramAPIError(None) from None
    try:
        body = response.json()
    except ValueError:
        raise TelegramAPIError(response.status_code) from None
    if not isinstance(body, dict) or response.status_code != 200 or body.get("ok") is not True:
        description = str(body.get("description", "")) if isinstance(body, dict) else ""
        raise TelegramAPIError(response.status_code, not_modified="message is not modified" in description.lower())
    return body.get("result")
