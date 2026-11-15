"""deliveries.effective_kind

Audit B-02: the outbox froze each delivery's effective config (V01) but still
chose the adapter from the live channel row's kind. Repurposing a channel (e.g.
webhook → ui) while a delivery was pending made the worker feed the frozen
webhook config to the ui adapter, which reported success — a false ``sent`` with
nothing delivered to the intended receiver. Freeze the adapter kind too, so
every attempt uses the adapter the delivery was admitted against.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-12 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column("effective_kind", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deliveries", "effective_kind")
