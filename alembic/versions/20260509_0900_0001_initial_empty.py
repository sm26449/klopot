"""initial empty migration (S1 — schema lands in S2)

Revision ID: 0001
Revises:
Create Date: 2026-05-09 09:00:00

This is an empty initial migration. It exists so the alembic_version
table is created on first run and S2 has a parent revision to attach
the real schema to.
"""
from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema changes — S2 will add the full set of tables in 0002."""
    pass


def downgrade() -> None:
    """Nothing to undo."""
    pass
