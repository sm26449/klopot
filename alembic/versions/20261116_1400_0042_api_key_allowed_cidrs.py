"""Per-key source allowlist: ``api_keys.allowed_cidrs``.

The addresses (IPs or CIDRs) a key may be used from; NULL or empty = any
address, which is what every existing key keeps. Checked on every request
after the key itself (app/auth.py).

Revision ID: 0042
Revises: 0041
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("allowed_cidrs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "allowed_cidrs")
