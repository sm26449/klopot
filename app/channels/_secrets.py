"""Helper: resolve secret references from channel config.

Per ``docs/SCHEMA.md``: sensitive fields use a ``_ref`` suffix and
store an environment variable NAME (not the value). Resolution at
runtime: ``os.environ[ref]``. This keeps secrets out of the DB and
out of git.

Usage in channel adapters::

    token = resolve_secret(config, "bot_token", "bot_token_ref")
    if token is None:
        return SendResult(ok=False, error="Missing bot_token_ref env var")
"""
from __future__ import annotations

import logging
import os
from typing import Any

from ..config import get_settings
from ..utils.secret_value import usable_secret

logger = logging.getLogger(__name__)


def resolve_secret(
    config: dict[str, Any],
    plain_key: str,
    ref_key: str,
) -> str | None:
    """Return the secret value, or None if missing.

    Resolution order:
      1. ``config[ref_key]`` — env var name; resolve via os.environ.
      2. ``config[plain_key]`` — literal value (development convenience).

    Production deployments should always use ``_ref`` so secrets
    never touch DB rows or git."""
    ref_name = config.get(ref_key)
    if ref_name:
        # Default-deny: a ref may only resolve an allowlisted env var, so it can
        # never be pointed at ALERTD_DATABASE_URL or another process secret and
        # exfiltrated through a channel header (audit S-04).
        if not get_settings().secret_ref_allowed(str(ref_name)):
            logger.warning(
                "secret ref %r is not allowlisted (name it KLOPOT_SECRET_..., or set ALERTD_SECRET_REF_ALLOW "
                "to permit it); refusing to resolve",
                ref_name,
            )
        else:
            val = os.environ.get(str(ref_name))
            if val:
                return usable_secret(val, f"env {ref_name}")
    plain = config.get(plain_key)
    if plain:
        return usable_secret(str(plain), f"field {plain_key}")
    return None


def scrub(text: str, *secrets: str | None) -> str:
    """Remove known secret values from an error string before it is stored on
    a delivery (readable with scope ``read``): an upstream may echo the token
    it was sent, and redact_url only catches URL-shaped credentials."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


# ── Errors fit to store (review K08) ───────────────────────────────

_MIN_SCRUB_LEN = 6
_URL_PREFIXES = ("http://", "https://", "mqtt://", "mqtts://", "ws://", "wss://")


def _looks_like_credential(segment: str) -> bool:
    """A URL path segment that may be a token: long, or mixed letters and
    digits. ``services`` or ``api`` stay readable in an error."""
    if len(segment) >= 12:
        return True
    return len(segment) >= 8 and any(c.isdigit() for c in segment) and any(c.isalpha() for c in segment)


def _url_secrets(url: str) -> set[str]:
    from urllib.parse import parse_qsl, urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return set()
    found: set[str] = set()
    if parts.password:
        found.add(parts.password)
    if len(parts.path) > 1:
        found.add(parts.path)
        found.update(s for s in parts.path.split("/") if _looks_like_credential(s))
    if parts.query:
        found.add(parts.query)
        found.update(v for _, v in parse_qsl(parts.query, keep_blank_values=True))
    return found


def channel_secret_strings(kind: str, config: dict[str, Any]) -> list[str]:
    """Every string of a channel's config that must not appear in a stored
    error: literal secrets, resolved ``*_ref`` values, custom header values,
    and the path, query and password of its URLs (a webhook path can be the
    credential). Longest first, so a whole path goes before its segments."""
    from ..secrets_registry import is_secret_key

    found: set[str] = set()
    for key, value in config.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue
        if key.endswith("_ref") and value:
            resolved = resolve_secret(config, key[: -len("_ref")], key)
            if resolved:
                found.add(resolved)
        elif isinstance(value, str) and value and is_secret_key("channel", kind, key):
            found.add(value)
        if key == "headers" and isinstance(value, dict):
            found.update(str(v) for v in value.values() if v)
        if isinstance(value, str) and value.lower().startswith(_URL_PREFIXES):
            found |= _url_secrets(value)
    return sorted((s for s in found if len(s) >= _MIN_SCRUB_LEN), key=len, reverse=True)


def scrub_error(text: str | None, secrets: list[str]) -> str | None:
    """``text`` with each of ``secrets`` replaced by ``***`` — also in the
    escaped forms an error repr shows (``\\n`` for a newline, ``\\x00`` …)."""
    if not text:
        return text
    for secret in secrets:
        for form in {secret, secret.encode("unicode_escape").decode("ascii"), repr(secret)[1:-1]}:
            if len(form) >= _MIN_SCRUB_LEN:
                text = text.replace(form, "***")
    return text
