"""Index ``deliveries.provider_ref`` (review K13).

The Pushover receipt poll runs every minute and looks for
``provider_ref LIKE 'pushover:receipt:%'``. Without an index that scanned the
delivery history (most rows are ``sent``); a prefix range on this index reads
the receipt rows only.

Revision ID: 0038
Revises: 0037
"""
from __future__ import annotations

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_delivery_provider_ref", "deliveries", ["provider_ref"])


def downgrade() -> None:
    op.drop_index("ix_delivery_provider_ref", table_name="deliveries")
