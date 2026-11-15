"""Provider failures never expose the token-bearing request URL."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.utils.telegram_api import TelegramAPIError, call_bot
from scripts.telegram_setup import discover


async def test_transport_error_discards_secret_url():
    leak = AsyncMock(side_effect=httpx.ConnectError("https://api.telegram.org/botSECRET/getUpdates"))
    with patch("app.utils.telegram_api.safe_request", leak):
        with pytest.raises(TelegramAPIError) as error:
            await call_bot("SECRET", "getUpdates", {})
    assert "SECRET" not in str(error.value)
    assert error.value.__suppress_context__


async def test_setup_displays_only_destination_ids(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET")
    updates = [{"message": {"chat": {"id": -100123}, "from": {"id": 42}, "text": "private message"}},
               {"message": {"chat": {"id": -100123}, "from": {"id": 42}}}]
    with patch("scripts.telegram_setup.call_bot", new_callable=AsyncMock,
               side_effect=[{"username": "klopot_bot"}, updates]) as api:
        result = await discover("TELEGRAM_BOT_TOKEN")
    assert result == {"bot_username": "klopot_bot", "destinations": [{"chat_id": "-100123", "user_id": "42"}]}
    assert api.await_args.args[2]["timeout"] == 0
    assert "offset" not in api.await_args.args[2]


async def test_call_bot_uses_the_configured_server_through_safe_http():
    from app.utils.telegram_api import api_url

    response = MagicMock(status_code=200)
    response.json.return_value = {"ok": True, "result": {"id": 1}}
    with patch("app.utils.telegram_api.safe_request", AsyncMock(return_value=response)) as req:
        assert await call_bot("T", "getMe", {}, base_url=api_url({"api_url": "https://bot.example/"})) == {"id": 1}
    assert req.call_args.args == ("POST", "https://bot.example/botT/getMe")
    assert api_url({}) == "https://api.telegram.org"
