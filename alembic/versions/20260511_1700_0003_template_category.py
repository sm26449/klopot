"""template_category

Adds a nullable ``category`` column to ``templates`` so the admin UI
can group templates (Battery / Grid / Inverter / PV / Consumption /
Climate / System / Internal). Existing rows get NULL, which the UI
renders as "Uncategorized" — operator assigns categories via the
edit modal at their own pace.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-11 17:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("category", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_templates_category", "templates", ["category"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_templates_category", table_name="templates")
    op.drop_column("templates", "category")
