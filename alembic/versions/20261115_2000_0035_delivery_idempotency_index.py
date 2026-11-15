"""Index ``deliveries.idempotency_key`` (audit P11).

The channel manager looks the delivery rows of a send up by this key — on
the first attempt and on every retry. Without an index that was a full scan
of ``deliveries`` each time: the cost of a fire grew with the delivery
history (~0.1 s on a small table, ~0.9 s at 1.4 million rows).

Revision ID: 0035
Revises: 0034
"""
from __future__ import annotations

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_delivery_idempotency_key", "deliveries", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_delivery_idempotency_key", table_name="deliveries")
