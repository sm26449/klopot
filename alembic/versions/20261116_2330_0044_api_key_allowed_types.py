"""Per-key allowed alert types: ``api_keys.allowed_types``.

Template types (or patterns like ``backup_*``) the key may fire through
POST /v1/fire; NULL = every type, which is what every existing key keeps.
Checked in the request (app/api/v1/fire.py) against the cached key.

Revision ID: 0044
Revises: 0043
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("allowed_types", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "allowed_types")
