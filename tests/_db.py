"""DB helpers for tests.

``fresh(session)`` — call it before re-reading rows that the app (another
session) may have committed since this test session last read. On MySQL the
test session keeps the REPEATABLE READ snapshot of its first query, so a
second read silently returns the old state (it passes on SQLite and fails in
the MySQL gate). Always use it instead of an ad-hoc ``rollback()``.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def fresh(session: AsyncSession) -> AsyncSession:
    """End the read snapshot and drop cached ORM state; returns the session."""
    await session.rollback()
    session.expire_all()
    return session


async def fresh_rows(session: AsyncSession, query: Any) -> list[Any]:
    """``fresh(session)`` then run ``query`` and return the scalars."""
    await fresh(session)
    return list((await session.execute(query)).scalars().all())
