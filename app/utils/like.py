"""Escape user input used inside a SQL ``LIKE`` pattern (audit S-19).

A raw search term goes straight into ``f"%{term}%"``, so a ``%`` or ``_`` the
user types acts as a wildcard — matching far more than intended and letting a
pathological pattern (``%a%a%a%…``) drive an expensive scan. Escape the LIKE
metacharacters and pass ``escape="\\"`` to ``.like()``.
"""
from __future__ import annotations

LIKE_ESCAPE = "\\"


def like_escape(term: str) -> str:
    """Escape ``\\``, ``%`` and ``_`` so ``term`` is matched literally."""
    return (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
