"""rules.state_epoch + rule_state.state_epoch

Audit B-06: a rule's match streak is reset live when its condition expression
changes, but the persisted ``rule_state`` row was only rewritten on the next
evaluation — a restart in that gap restored a streak counted against the old
expression. These two monotonic epochs let the reset be durable and race-safe:
the expression change bumps ``rules.state_epoch`` and stamps the reset
``rule_state`` row with it, and cold start trusts a persisted streak only when
its epoch still matches the rule's (so a stale runtime's late write-back, which
carries the old epoch, is ignored).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-11 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("state_epoch", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "rule_state",
        sa.Column("state_epoch", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("rule_state", "state_epoch")
    op.drop_column("rules", "state_epoch")
