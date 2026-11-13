"""escalation

Escalation on unacknowledged criticals (hardening plan phase 5):

- ``notifications_log.escalated_at`` — when the escalation service
  re-paged this row to the escalation channel (NULL = never).
- ``notifications_log.is_test`` — marks test fires so they never
  escalate and can be filtered in the log.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-06 21:45:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications_log",
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "notifications_log",
        sa.Column(
            "is_test", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
    )


def downgrade() -> None:
    op.drop_column("notifications_log", "is_test")
    op.drop_column("notifications_log", "escalated_at")
