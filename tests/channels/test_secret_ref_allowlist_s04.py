"""S-04: a channel/input ``*_ref`` must resolve only allowlisted env vars, so a
config author can't point a ref at ALERTD_DATABASE_URL (or another process
secret) and exfiltrate it through a channel header."""
from __future__ import annotations

from app.channels._secrets import resolve_secret
from app.config import get_settings


def test_allowlisted_ref_resolves(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-123")
    val = resolve_secret({"bot_token_ref": "TELEGRAM_BOT_TOKEN"}, "bot_token", "bot_token_ref")
    assert val == "tok-123"


def test_non_allowlisted_ref_is_refused(monkeypatch):
    # The env var exists, but it is not on the allowlist → refused (None).
    monkeypatch.setenv("ALERTD_DATABASE_URL", "mysql+aiomysql://u:p@h/db")
    val = resolve_secret({"bot_token_ref": "ALERTD_DATABASE_URL"}, "bot_token", "bot_token_ref")
    assert val is None


def test_arbitrary_env_var_refused(monkeypatch):
    monkeypatch.setenv("SOME_RANDOM_SECRET", "nope")
    val = resolve_secret({"x_ref": "SOME_RANDOM_SECRET"}, "x", "x_ref")
    assert val is None


def test_literal_value_still_works():
    # The plaintext convenience path is independent of the allowlist.
    assert resolve_secret({"bot_token": "literal"}, "bot_token", "bot_token_ref") == "literal"


def test_operator_can_extend_allowlist(monkeypatch):
    monkeypatch.setenv("ALERTD_SECRET_REF_ALLOW", "MY_CUSTOM_SECRET")
    monkeypatch.setenv("MY_CUSTOM_SECRET", "custom-val")
    get_settings.cache_clear()
    try:
        val = resolve_secret({"x_ref": "MY_CUSTOM_SECRET"}, "x", "x_ref")
        assert val == "custom-val"
    finally:
        get_settings.cache_clear()
