"""Rule run state and its history (rules review RL-32).

``rules.run_state`` / ``run_state_since`` / ``last_true_at``: where a rule is
in its cycle (inactive, pending, firing, no_data, error), written by the
engine on a change only. ``rule_transitions``: one row per change, pruned
with the log. Existing rules start with NULL (unknown until their next
evaluation).

Revision ID: 0045
Revises: 0044
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("run_state", sa.String(16), nullable=True))
    op.add_column("rules", sa.Column("run_state_since", sa.DateTime(), nullable=True))
    op.add_column("rules", sa.Column("last_true_at", sa.DateTime(), nullable=True))
    op.create_table(
        "rule_transitions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.BigInteger(), sa.ForeignKey("rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("from_state", sa.String(16), nullable=True),
        sa.Column("to_state", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(255), nullable=True),
    )
    op.create_index("ix_rule_transitions_rule", "rule_transitions", ["rule_id", "id"])
    op.create_index("ix_rule_transitions_at", "rule_transitions", ["at"])


def downgrade() -> None:
    op.drop_index("ix_rule_transitions_at", table_name="rule_transitions")
    op.drop_index("ix_rule_transitions_rule", table_name="rule_transitions")
    op.drop_table("rule_transitions")
    op.drop_column("rules", "last_true_at")
    op.drop_column("rules", "run_state_since")
    op.drop_column("rules", "run_state")
