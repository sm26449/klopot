"""Template categories: one spelling per category.

Categories are free text. A value that differs from an existing category
only by case ("grid" vs "Grid") is stored with the spelling already in use,
so the admin UI's grouping never splits. Used by the templates API and by
config import.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Template
from ..utils.icons import normalize_category


async def canonical_category(
    session: AsyncSession, value: str | None, *, exclude_type: str | None = None,
) -> str | None:
    """Trimmed ``value`` in the most used existing spelling (case-insensitive
    match), or ``value`` itself when it is new. Counted in Python: MySQL's
    case-insensitive collation would merge the variants in a GROUP BY."""
    value = normalize_category(value)
    if not value:
        return value
    query = select(Template.category).where(Template.category.is_not(None))
    if exclude_type is not None:
        query = query.where(Template.type != exclude_type)
    counts = Counter(c for (c,) in (await session.execute(query)).all() if c.lower() == value.lower())
    return counts.most_common(1)[0][0] if counts else value
