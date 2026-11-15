"""Validation for template icons and categories.

An icon is a short emoji (``⚠️``, ``🔋``, ``☀️``). Free text used to reach the
DB unchecked, and production ended up with mojibake such as ``âš¡`` / ``ðŸš¨``
(UTF-8 emoji decoded as Latin-1 somewhere upstream) and ``??`` (a lost
emoji). Those all contain letters or question marks and no pictographic
symbol, which is what this check rejects.
"""
from __future__ import annotations

import unicodedata

_FORBIDDEN = {"?", "�"}  # lost character, replacement character


def validate_icon(value: str | None) -> str | None:
    """Return the stripped icon (``None`` for empty) or raise ``ValueError``."""
    if value is None:
        return None
    icon = value.strip()
    if not icon:
        return None
    has_symbol = False
    for ch in icon:
        category = unicodedata.category(ch)
        if ch in _FORBIDDEN or category[0] in ("L", "N"):
            raise ValueError(
                f"icon must be an emoji (got {icon!r}, which contains text — "
                "possibly a mis-encoded emoji)"
            )
        if category == "So":
            has_symbol = True
    if not has_symbol:
        raise ValueError(f"icon must be an emoji (got {icon!r})")
    return icon


def normalize_category(value: str | None) -> str | None:
    """Trim and collapse whitespace; empty → ``None`` (uncategorized)."""
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None
