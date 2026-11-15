"""dedup_claims

Audit R01: an atomic fire-admission claim table so two concurrent fires of
the same (type, is_test, context) can't both pass the SELECT-based dedup and
each create a notification. One row per (type, is_test, context_hash); a fire
claims its slot with an upsert that only overwrites a stale claim.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-08 21:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dedup_claims",
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False),
        sa.Column("context_hash", sa.String(16), nullable=False),
        sa.Column("notification_id", sa.String(64), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("type", "is_test", "context_hash"),
    )
    op.create_index("ix_dedup_claimed_at", "dedup_claims", ["claimed_at"])


def downgrade() -> None:
    op.drop_index("ix_dedup_claimed_at", table_name="dedup_claims")
    op.drop_table("dedup_claims")
