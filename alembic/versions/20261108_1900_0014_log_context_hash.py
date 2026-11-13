"""log_context_hash

Audit F24: persist a canonical context hash on each notification log row and
index (type, is_test, context_hash, fired_at) so idempotency dedup matches by
context directly in SQL. The previous dedup fetched only the 5 most recent
rows for (type, is_test) and filtered in Python, so an in-window duplicate was
missed once more than five distinct contexts fired for the same type.

Additive and reversible. Existing rows keep context_hash NULL; the dedup
window is minutes, so they age out shortly after deploy (no backfill needed).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-08 19:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications_log",
        sa.Column("context_hash", sa.String(16), nullable=True),
    )
    op.create_index(
        "ix_log_dedup", "notifications_log",
        ["type", "is_test", "context_hash", "fired_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_log_dedup", table_name="notifications_log")
    op.drop_column("notifications_log", "context_hash")
