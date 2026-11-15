"""Telegram action policy and public links; independent of transport and DB."""
from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import quote, urlsplit

_INTEGER = re.compile(r"-?[1-9][0-9]*\Z")


def bot_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def numeric_id(value: Any, *, positive: bool = False) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    text = str(value)
    if not _INTEGER.fullmatch(text) or len(text) > 20:
        return None
    number = int(text)
    if not -(2**63) < number < 2**63 or (positive and number <= 0):
        return None
    return str(number)


def allowed_users(config: dict[str, Any]) -> list[str]:
    values = config.get("allowed_user_ids")
    if values is None:
        values = []
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("allowed_user_ids must be a JSON array with at most 100 user IDs")
    ids = [numeric_id(v, positive=True) for v in values]
    if any(v is None for v in ids):
        raise ValueError("allowed_user_ids must contain positive integer user IDs")
    return sorted({v for v in ids if v is not None})


def actor_allowed(config: dict[str, Any], user_id: str) -> bool:
    users = allowed_users(config)
    # An explicit allowlist always wins over the broad chat-member opt-in.
    return user_id in users if users else config.get("any_chat_member") is True


def validate_actions_config(config: dict[str, Any]) -> None:
    for key in ("inline_actions", "any_chat_member"):
        if key in config and not isinstance(config[key], bool):
            raise ValueError(f"{key} must be a boolean")
    users = allowed_users(config)
    if config.get("actions_locale", "en") not in ("en", "ro"):
        raise ValueError("actions_locale must be en or ro")
    if config.get("inline_actions") is True:
        if numeric_id(config.get("chat_id")) is None:
            raise ValueError("inline_actions requires a numeric chat_id")
        if not users and config.get("any_chat_member") is not True:
            raise ValueError("inline_actions requires allowed_user_ids or explicit any_chat_member=true")
    url = config.get("admin_url")
    if url:
        if not isinstance(url, str) or len(url) > 1000:
            raise ValueError("admin_url must be an absolute HTTP(S) admin URL")
        try:
            parts = urlsplit(url)
            valid = parts.scheme in ("http", "https") and bool(parts.hostname) and not (
                parts.username or parts.password or parts.query or parts.fragment
            )
            _ = parts.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("admin_url must be an absolute HTTP(S) URL without credentials, query or fragment")


def public_view_url(config: dict[str, Any], notification_id: str, incident_id: str | None) -> str | None:
    base = config.get("admin_url")
    if not base:
        return None
    validate_actions_config(config)
    target = f"incidents/{quote(incident_id, safe='')}" if incident_id else f"log?id={quote(notification_id, safe='')}"
    return f"{base.rstrip('/')}/#/{target}"


_LABELS = {
    "en": {"ack": "Acknowledge", "snooze_1h": "Snooze 1h", "snooze_morning": "Snooze until {hour:02d}:00", "view": "Open in Klopot"},
    "ro": {"ack": "Confirmă", "snooze_1h": "Amână 1h", "snooze_morning": "Amână până la {hour:02d}:00", "view": "Deschide în Klopot"},
}


def action_labels(locale: str | None) -> dict[str, str]:
    """Button labels in ``locale`` (English when unknown); the morning hour
    comes from ALERTD_SNOOZE_MORNING_HOUR, the same one snooze_deadline uses."""
    from ..config import get_settings

    hour = get_settings().snooze_morning_hour
    return {k: v.format(hour=hour) for k, v in _LABELS.get(locale or "en", _LABELS["en"]).items()}
