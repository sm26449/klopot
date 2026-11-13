"""delivery_channel_overrides

Audit F03: persist the effective per-route channel overrides on each
delivery so a retry delivers to the same destination as the first attempt
even if the route is edited meanwhile.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-08 16:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deliveries", sa.Column("channel_overrides", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("deliveries", "channel_overrides")
