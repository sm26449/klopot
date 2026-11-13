"""notifications_log.success_counted

Audit V08: an idempotent marker that a fire's first successful delivery has
already been accounted (template throttle + rule lifetime counter). Set exactly
once via compare-and-set, independent of the channel list and the rollup status,
so a partial synchronous success followed by a retry is neither dropped nor
double-counted.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-09 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications_log",
        sa.Column(
            "success_counted",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("notifications_log", "success_counted")
