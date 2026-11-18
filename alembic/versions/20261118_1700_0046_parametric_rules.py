"""Parametric rules (ADR-0005).

``rules.for_each`` (JSON, NULL = an ordinary rule); ``rule_instances``, the
runtime state of each instance of a parametric rule; ``rule_transitions.instance``
("" for an ordinary rule). Additive: existing rules, their ``rule_state`` and
their incidents are untouched (an instance's open incident uses the existing
``incidents.active_source_key`` as ``rule:<id>:<instance>``).

Revision ID: 0046
Revises: 0045
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("for_each", sa.JSON(), nullable=True))
    op.add_column("rule_transitions",
                  sa.Column("instance", sa.String(32), nullable=False, server_default=""))
    op.create_table(
        "rule_instances",
        sa.Column("rule_id", sa.BigInteger(), sa.ForeignKey("rules.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("instance", sa.String(32), primary_key=True),
        sa.Column("consecutive_match_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovery_match_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_state", sa.String(16), nullable=True),
        sa.Column("run_state_since", sa.DateTime(), nullable=True),
        sa.Column("last_true_at", sa.DateTime(), nullable=True),
        sa.Column("last_eval_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("rule_instances")
    op.drop_column("rule_transitions", "instance")
    op.drop_column("rules", "for_each")
