"""Separate escalation deliveries from initial deliveries.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-13 12:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column("purpose", sa.String(length=16), nullable=False, server_default="notification"),
    )
    # Add the wider key first: it also keeps the notification FK indexed
    # while MySQL drops the old unique index.
    op.create_unique_constraint(
        "uq_delivery_notif_channel_purpose", "deliveries",
        ["notification_id", "channel", "purpose"],
    )
    op.drop_constraint("uq_delivery_notif_channel", "deliveries", type_="unique")
    op.alter_column(
        "deliveries", "state",
        existing_type=sa.Enum("pending", "sent", "failed"),
        type_=sa.Enum("pending", "sent", "failed", "cancelled"),
        existing_nullable=False,
    )


def downgrade() -> None:
    raise RuntimeError(
        "Durable escalation is forward-only: restore the pre-deploy database backup."
    )
