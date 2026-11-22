"""Alert explanation (week audit 2026-11-21, stage C2): ``notifications_log.explain``.

What the dispatcher decided and why, recorded when the alert fired — the
gates it went through (snooze, throttle, delivery gate, quiet hours) with
what each saw, the channels routed and kept, and for a rule fire the rule's
condition, instance and the values it read. Read by ``GET /v1/log/{id}/trace``.
Additive and nullable: older rows have none (their trace is reconstructed).

Revision ID: 0047
Revises: 0046
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications_log", sa.Column("explain", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications_log", "explain")
