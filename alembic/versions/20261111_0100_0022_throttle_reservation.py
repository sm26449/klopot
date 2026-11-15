"""throttle_state.reserved_at + reserved_by

Audit B-10: the per-type cooldown (min_repeat_min) was anchored only on the last
*successful* fire, so two distinct-context fires that raced before the first
success both passed the throttle and both sent. These columns hold an in-flight
admission reservation taken atomically in the durable-intent transaction, so the
cooldown boundary is enforced at admission (released on terminal failure,
superseded by last_fired_at on success).

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-11 01:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("throttle_state", sa.Column("reserved_at", sa.DateTime(), nullable=True))
    op.add_column("throttle_state", sa.Column("reserved_by", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("throttle_state", "reserved_by")
    op.drop_column("throttle_state", "reserved_at")
