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
        if str(ref_name) not in get_settings().secret_ref_allow_set:
            logger.warning(
                "secret ref %r is not allowlisted (set ALERTD_SECRET_REF_ALLOW "
                "to permit it); refusing to resolve",
                ref_name,
            )
        else:
            val = os.environ.get(str(ref_name))
            if val:
                return val
    plain = config.get(plain_key)
    if plain:
        return str(plain)
    return None
