"""Startup-sequence contracts for the FastAPI lifespan."""
from __future__ import annotations

import pytest

from app import main


async def test_lifespan_fails_fast_on_migration_error(monkeypatch) -> None:
    """A failed Alembic upgrade must abort startup (propagate), not
    leave the service running on a half-migrated schema. Docker's
    restart policy turns this into a visible restart loop."""

    def boom() -> None:
        raise RuntimeError("migration exploded")

    monkeypatch.setattr(main, "_run_migrations_sync", boom)
    app = main.create_app()
    with pytest.raises(RuntimeError, match="migration exploded"):
        async with main.lifespan(app):
            pass
