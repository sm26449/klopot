"""delivery_outbox

Audit A01: transactional outbox. A ``deliveries`` row per (notification,
channel) is written in the same transaction as the NotificationLog,
BEFORE any external send, and a background worker retries ``pending``
rows with backoff (at-least-once). ``notifications_log.delivery_status``
gains a ``pending`` value so a not-yet-settled fire is visible as such.

Revision ID: 0011
Revises: 0009
Create Date: 2026-11-08 14:00:00

NOTE: if the A34 migration 0010 lands first, re-point ``down_revision``
to "0010" (both currently revise 0009 on their own branches).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DS_OLD = "'sent','partial','failed','suppressed'"
_DS_NEW = _DS_OLD + ",'pending'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE notifications_log MODIFY delivery_status "
        f"ENUM({_DS_NEW}) NULL"
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.Enum("pending", "sent", "failed", name="deliverystate"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=130), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications_log.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "channel", name="uq_delivery_notif_channel"),
    )
    op.create_index("ix_delivery_due", "deliveries", ["state", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_delivery_due", table_name="deliveries")
    op.drop_table("deliveries")
    op.execute(
        "UPDATE notifications_log SET delivery_status = NULL "
        "WHERE delivery_status = 'pending'"
    )
    op.execute(
        "ALTER TABLE notifications_log MODIFY delivery_status "
        f"ENUM({_DS_OLD}) NULL"
    )
