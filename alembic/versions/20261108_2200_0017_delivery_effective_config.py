"""delivery_effective_config

Audit V01: freeze the full effective destination config on each delivery at
enqueue time, so every retry targets the SAME destination/credentials as the
first attempt even if the channel's base config is edited meanwhile. F03 only
froze the per-route override delta; the base config was still read live, so an
admin editing a channel's URL/chat/phone/token between attempts redirected the
retry — a misdelivery/disclosure risk.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-08 22:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column("effective_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deliveries", "effective_config")
