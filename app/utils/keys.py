"""Keys that must fit a column."""
from __future__ import annotations

import hashlib

# ``incidents.source_key`` / ``active_source_key`` are VARCHAR(191).
SOURCE_KEY_MAX = 191
_DIGEST_CHARS = 40


def bounded_key(key: str, limit: int = SOURCE_KEY_MAX) -> str:
    """``key`` unchanged when it fits ``limit``; otherwise its head plus a
    digest of the whole, exactly ``limit`` characters.

    Stable (the same long key always maps to the same result, so an episode
    is found again) and distinct for keys that differ only past the head.
    MySQL rejects an over-long value outright; SQLite would store it.
    """
    if len(key) <= limit:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]
    return f"{key[: limit - _DIGEST_CHARS - 1]}:{digest}"
