"""Async SQLAlchemy session management.

Single engine + session factory built once at app startup, disposed
on shutdown. Each request gets a session via FastAPI dependency
injection (``get_session``), which manages commit/rollback semantics.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import get_settings

# Module-level engine and session factory — created at startup.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _connect_args(database_url: str) -> dict[str, object]:
    """DBAPI connect_args for the engine.

    On MySQL, force every pooled connection's session time zone to UTC so
    ``CURRENT_TIMESTAMP`` server defaults (``created_at``/``updated_at``
    across the config tables) are stored as UTC regardless of the MySQL
    container's OS ``TZ`` — which stays local on purpose, for quiet-hours
    evaluation that reads Python ``datetime.now()`` (B-13). Without this,
    a row created at 09:00 UTC was stored as the container-local wall time
    and then served with a ``Z`` suffix, misdated by the offset.

    The guard keeps SQLite (tests) and any non-MySQL backend untouched —
    ``SET time_zone`` / ``init_command`` are MySQL-only.
    """
    if database_url.startswith("mysql"):
        return {"init_command": "SET time_zone = '+00:00'"}
    return {}


def init_engine() -> None:
    """Create the engine + session factory. Idempotent."""
    global _engine, _session_factory
    if _engine is not None:
        return

    settings = get_settings()
    database_url = settings.require_database_url()
    _engine = create_async_engine(
        database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # validate connections from the pool
        pool_recycle=3600,    # recycle hourly to dodge MySQL wait_timeout
        connect_args=_connect_args(database_url),
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def dispose_engine() -> None:
    """Close the engine + session factory. Called on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    """Module accessor for components that need raw engine access
    (e.g., Alembic at runtime). Raises if not initialized."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Module accessor for background tasks that need a session
    outside the request lifecycle (e.g. retention sweep). Caller is
    responsible for ``async with factory() as session``."""
    if _session_factory is None:
        raise RuntimeError("Database session factory not initialized.")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async session per request.

    On exception inside the handler, rolls back. On success, commits.
    Either way, closes the session and returns it to the pool.

    Usage::

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            result = await session.execute(...)
            return result.scalars().all()
    """
    if _session_factory is None:
        raise RuntimeError("Database session factory not initialized.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise
        except Exception:
            # Non-DB exceptions also roll back to avoid leaking pending writes
            await session.rollback()
            raise


async def healthcheck() -> tuple[bool, str | None]:
    """Probe the database with ``SELECT 1``.

    Returns (ok, error_msg). Used by /v1/health.
    """
    if _engine is None:
        return False, "engine not initialized"
    try:
        from sqlalchemy import text

        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except SQLAlchemyError as e:
        return False, str(e)[:200]
