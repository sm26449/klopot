"""Identify a new dedicated bot's chat/user IDs without printing its token.

Send /start to the bot, then run inside the Klopot container before enabling
inline_actions: python -m scripts.telegram_setup --token-ref TELEGRAM_BOT_TOKEN
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.channels._secrets import resolve_secret
from app.channels.telegram_config import numeric_id
from app.utils.telegram_api import TelegramAPIError, call_bot


async def discover(token_ref: str) -> dict[str, Any]:
    token = resolve_secret({"bot_token_ref": token_ref}, "bot_token", "bot_token_ref")
    if not token:
        raise ValueError("Bot token unavailable; export the allowlisted variable or run inside the Klopot container")
    me = await call_bot(token, "getMe", {})
    updates = await call_bot(token, "getUpdates", {"timeout": 0, "limit": 100, "allowed_updates": ["message"]})
    chats = set()
    for update in updates if isinstance(updates, list) else []:
        if not isinstance(update, dict):
            continue
        message = update.get("message") or {}
        if not isinstance(message, dict):
            continue
        chat = numeric_id((message.get("chat") or {}).get("id"))
        user = numeric_id((message.get("from") or {}).get("id"), positive=True)
        if chat and user:
            chats.add((chat, user))
    return {"bot_username": me.get("username") if isinstance(me, dict) else None,
            "destinations": [{"chat_id": chat, "user_id": user} for chat, user in sorted(chats)]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-ref", default="TELEGRAM_BOT_TOKEN")
    args = parser.parse_args()
    try:
        result = asyncio.run(discover(args.token_ref))
    except (ValueError, TelegramAPIError) as error:
        print(str(error))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["destinations"]:
        print("Send /start to the dedicated bot, then run this command again before enabling inline_actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
