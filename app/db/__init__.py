"""Database layer — SQLAlchemy 2.0 async.

Public surface (used by api/, core/):

    from app.db import Base, get_session

The ORM models live in ``models.py``; the session factory lives in
``session.py``. Migrations are managed by Alembic — see
``alembic/env.py``.
"""
from __future__ import annotations

from .base import Base
from .session import (
    affected_rows,
    dispose_engine,
    get_session,
    get_session_factory,
    init_engine,
)

__all__ = [
    "Base",
    "affected_rows",
    "dispose_engine",
    "get_session",
    "get_session_factory",
    "init_engine",
]
