"""schedule_occurrences

Audit V05: a fired-occurrence guard for cron schedules. One row per
(schedule_id, scheduled_at), inserted in the same transaction that advances
next_fire_at and persists the notification intent, so a given occurrence fires
at most once even under a double-tick or a second instance — the composite
primary key rejects the duplicate.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-08 23:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_occurrences",
        sa.Column("schedule_id", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("notification_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.func.current_timestamp(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["schedules.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("schedule_id", "scheduled_at"),
    )
    op.create_index(
        "ix_schedule_occ_scheduled_at", "schedule_occurrences", ["scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_occ_scheduled_at", table_name="schedule_occurrences")
    op.drop_table("schedule_occurrences")
