"""Per-key rate limit: ``api_keys.rate_limit_per_min``.

Requests a minute the key may make; NULL = no limit, which is what every
existing key keeps. Enforced in the process on every request with the key
(app/auth.py, app/utils/rate_limit.py).

Revision ID: 0043
Revises: 0042
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("rate_limit_per_min", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "rate_limit_per_min")
