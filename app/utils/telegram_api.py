"""Bounded Bot API calls to Telegram's fixed HTTPS origin."""
from __future__ import annotations

from typing import Any

import httpx


class TelegramAPIError(Exception):
    def __init__(self, status: int | None, *, not_modified: bool = False) -> None:
        super().__init__(f"Telegram HTTP {status}" if status else "Telegram transport error")
        self.status = status
        self.not_modified = not_modified


async def call_bot(token: str, method: str, payload: dict[str, Any], *, io_timeout: float = 10) -> Any:
    if method not in {"getUpdates", "getMe", "answerCallbackQuery", "editMessageReplyMarkup"}:
        raise ValueError("unsupported Bot API method")
    try:
        async with httpx.AsyncClient(timeout=io_timeout, follow_redirects=False) as client:
            response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
    except httpx.HTTPError:
        # Exception URLs can contain the bot token. Do not retain the cause.
        raise TelegramAPIError(None) from None
    if len(response.content) > 2 * 1024 * 1024:
        raise TelegramAPIError(None)
    try:
        body = response.json()
    except ValueError:
        raise TelegramAPIError(response.status_code) from None
    if not isinstance(body, dict) or response.status_code != 200 or body.get("ok") is not True:
        description = str(body.get("description", "")) if isinstance(body, dict) else ""
        raise TelegramAPIError(response.status_code, not_modified="message is not modified" in description.lower())
    return body.get("result")
