"""Rule incidents and recovery conditions.

Revision ID: 0025
Revises: 0024
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("incident_enabled", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("rules", sa.Column("recovery_expr", sa.Text(), nullable=True))
    op.add_column("rules", sa.Column("recovery_persist_n", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("rules", sa.Column("resolved_template_type", sa.String(64), nullable=True))
    op.add_column("rule_state", sa.Column("recovery_match_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("rule_id", sa.BigInteger(), sa.ForeignKey("rules.id", ondelete="SET NULL")),
        sa.Column("active_rule_id", sa.BigInteger(), sa.ForeignKey("rules.id", ondelete="SET NULL"), unique=True),
        sa.Column("rule_name", sa.String(128), nullable=False),
        sa.Column("template_type", sa.String(64), nullable=False),
        sa.Column("resolved_template_type", sa.String(64)),
        sa.Column("severity", sa.Enum("info", "warning", "critical"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("resolution_reason", sa.String(500)),
        sa.Column("acknowledged_at", sa.DateTime()),
        sa.Column("acknowledged_by", sa.String(64)),
        sa.Column("opening_context", sa.JSON(), nullable=False),
        sa.Column("resolution_context", sa.JSON()),
    )
    op.create_index("ix_incident_resolved_opened", "incidents", ["resolved_at", "opened_at"])
    op.create_index("ix_incident_rule_opened", "incidents", ["rule_id", "opened_at"])
    op.add_column("notifications_log", sa.Column("incident_id", sa.String(64)))
    op.add_column("notifications_log", sa.Column("incident_event", sa.String(16)))
    op.create_foreign_key("fk_log_incident", "notifications_log", "incidents", ["incident_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_notifications_log_incident_id", "notifications_log", ["incident_id"])
    op.alter_column(
        "notifications_log", "delivery_status", existing_nullable=True,
        existing_type=sa.Enum("sent", "partial", "failed", "suppressed", "pending"),
        type_=sa.Enum("sent", "partial", "failed", "suppressed", "pending", "cancelled"),
    )


def downgrade() -> None:
    raise RuntimeError("Incident migration is forward-only; restore the pre-deploy backup.")
