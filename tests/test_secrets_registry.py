"""Pure-unit tests for ``app.secrets_registry`` (audit 2026-11-07 C-1/C-2)."""
from __future__ import annotations

from app.db.models import ChannelKind, InputKind
from app.secrets_registry import (
    MASK,
    is_secret_key,
    mask_config,
    merge_secret_update,
    secret_status,
)

# ── is_secret_key ─────────────────────────────────────────────────


def test_registered_fields_are_secret():
    assert is_secret_key("channel", "telegram", "bot_token")
    assert is_secret_key("channel", ChannelKind.email, "password")
    assert is_secret_key("input", InputKind.mqtt, "password")
    assert is_secret_key("input", "mqtt", "username")
    assert is_secret_key("input", "webhook", "auth_token")
    assert is_secret_key("input", "sms_inbox", "auth_token")


def test_ref_siblings_and_flags_are_not_secret():
    assert not is_secret_key("channel", "telegram", "bot_token_ref")
    assert not is_secret_key("channel", "telegram", "chat_id")
    assert not is_secret_key("input", "webhook", "auth_required")
    assert not is_secret_key("channel", "webhook", "auth_kind")


def test_heuristic_catches_unregistered_kind():
    assert is_secret_key("channel", "future_kind", "api_token")
    assert is_secret_key("channel", "future_kind", "client_secret")
    assert not is_secret_key("channel", "future_kind", "url")


# ── mask_config ───────────────────────────────────────────────────


def test_mask_replaces_literal_keeps_ref_and_plain():
    cfg = {"host": "broker", "port": 1883, "username": "u", "password": "p",
           "password_ref": "ALERTD_MQTT_PASSWORD"}
    out = mask_config("input", "mqtt", cfg)
    assert out == {"host": "broker", "port": 1883, "username": MASK, "password": MASK,
                   "password_ref": "ALERTD_MQTT_PASSWORD"}
    # input untouched
    assert cfg["password"] == "p"


def test_mask_leaves_empty_secret_alone():
    assert mask_config("channel", "telegram", {"bot_token": "", "chat_id": "1"}) == {
        "bot_token": "", "chat_id": "1"}


def test_mask_handles_none():
    assert mask_config("channel", "ui", None) == {}


# ── secret_status ─────────────────────────────────────────────────


def test_status_reports_env_ref_literal_and_omits_unset():
    cfg = {"chat_id": "1", "bot_token_ref": "TELEGRAM_BOT_TOKEN"}
    assert secret_status("channel", "telegram", cfg) == {"bot_token": "env:TELEGRAM_BOT_TOKEN"}
    assert secret_status("channel", "telegram", {"bot_token": "123:abc"}) == {"bot_token": "literal"}
    assert secret_status("channel", "telegram", {"chat_id": "1"}) == {}


def test_status_ref_takes_precedence_and_keeps_scheme():
    cfg = {"password": "x", "password_ref": "secret:smtp_main"}
    assert secret_status("channel", "email", cfg) == {"password": "secret:smtp_main"}


def test_status_includes_heuristic_literals_on_unknown_kind():
    assert secret_status("channel", "future", {"api_token": "t"}) == {"api_token": "literal"}


# ── merge_secret_update ───────────────────────────────────────────

_OLD = {"smtp_host": "h", "username": "u", "password": "old-pw", "to": ["a@b"]}


def test_merge_omitted_secret_keeps_old():
    new = {"smtp_host": "h2", "username": "u", "to": ["a@b"]}
    out = merge_secret_update("channel", "email", _OLD, new)
    assert out["smtp_host"] == "h2"
    assert out["password"] == "old-pw"


def test_merge_null_secret_keeps_old():
    out = merge_secret_update("channel", "email", _OLD, {**_OLD, "password": None})
    assert out["password"] == "old-pw"


def test_merge_masked_echo_keeps_old():
    out = merge_secret_update("channel", "email", _OLD, {**_OLD, "password": MASK})
    assert out["password"] == "old-pw"


def test_merge_empty_string_clears():
    out = merge_secret_update("channel", "email", _OLD, {**_OLD, "password": ""})
    assert "password" not in out


def test_merge_new_value_replaces():
    out = merge_secret_update("channel", "email", _OLD, {**_OLD, "password": "new-pw"})
    assert out["password"] == "new-pw"


def test_merge_non_secret_keys_are_wholesale_replaced():
    out = merge_secret_update("channel", "email", _OLD, {"smtp_host": "only"})
    assert out == {"smtp_host": "only", "password": "old-pw"}


def test_merge_no_old_secret_and_omitted_stays_absent():
    out = merge_secret_update("channel", "telegram", {"chat_id": "1"}, {"chat_id": "2"})
    assert out == {"chat_id": "2"}


# ── F17: nested masked secrets must not overwrite real credentials ─────

def test_merge_nested_masked_header_keeps_old():
    old = {"url": "https://x", "headers": {"Authorization": "Bearer real"}}
    # Client echoes the masked read back while changing an unrelated field.
    new = {"url": "https://y", "headers": {"Authorization": MASK}}
    out = merge_secret_update("channel", "webhook", old, new)
    assert out["url"] == "https://y"
    assert out["headers"]["Authorization"] == "Bearer real"


def test_merge_nested_omitted_header_secret_is_preserved():
    old = {"headers": {"Authorization": "Bearer real", "X-Trace": "1"}}
    new = {"headers": {"X-Trace": "2"}}  # Authorization omitted
    out = merge_secret_update("channel", "webhook", old, new)
    assert out["headers"]["Authorization"] == "Bearer real"
    assert out["headers"]["X-Trace"] == "2"


def test_merge_nested_empty_header_secret_clears():
    old = {"headers": {"Authorization": "Bearer real"}}
    new = {"headers": {"Authorization": ""}}
    out = merge_secret_update("channel", "webhook", old, new)
    assert "Authorization" not in out["headers"]


def test_merge_nested_new_header_secret_replaces():
    old = {"headers": {"Authorization": "Bearer real"}}
    new = {"headers": {"Authorization": "Bearer fresh"}}
    out = merge_secret_update("channel", "webhook", old, new)
    assert out["headers"]["Authorization"] == "Bearer fresh"


def test_merge_nested_secret_inside_list_preserved():
    old = {"hooks": [{"x-api-key": "secret1"}, {"x-api-key": "secret2"}]}
    new = {"hooks": [{"x-api-key": MASK}, {"x-api-key": MASK}]}
    out = merge_secret_update("channel", "webhook", old, new)
    assert out["hooks"][0]["x-api-key"] == "secret1"
    assert out["hooks"][1]["x-api-key"] == "secret2"
