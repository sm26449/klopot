"""Web Push devices: one row per browser / installed app (docs/WEB_PUSH.md).

Replaces ``user_prefs.settings.push_subscriptions`` (never populated in
production): per-device label, minimum severity, enabled flag and delivery
state, unique by ``endpoint_hash`` (sha256 of the endpoint URL).

Revision ID: 0033
Revises: 0032
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("endpoint", sa.String(1024), nullable=False),
        sa.Column("endpoint_hash", sa.String(64), nullable=False),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("min_severity", sa.Enum("info", "warning", "critical", name="severity"),
                  nullable=False, server_default="warning"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("endpoint_hash", name="uq_push_subscriptions_endpoint_hash"),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
