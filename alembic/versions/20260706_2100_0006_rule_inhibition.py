"""rule_inhibition

Alertmanager-style inhibition (hardening plan 2026-07-06, phase 4):

- ``rules.inhibited_by`` — JSON list of rule NAMES whose active state
  suppresses this rule's fires. One root cause (broker down) pages
  once instead of cascading through every dependent freshness rule.
- ``notifications_log.suppressed_reason`` gains the ``inhibited``
  enum value so suppressed fires stay visible in the log/digest.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-06 21:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_OLD = "'disabled','snoozed','throttled','persist','gated','duplicate','unknown_type'"
_ENUM_NEW = _ENUM_OLD + ",'inhibited'"


def upgrade() -> None:
    # Three steps because MySQL JSON columns have no implicit default:
    # a direct ADD COLUMN ... NOT NULL fails on a populated table.
    op.add_column(
        "rules",
        sa.Column("inhibited_by", sa.JSON(), nullable=True),
    )
    op.execute("UPDATE rules SET inhibited_by = JSON_ARRAY()")
    op.execute("ALTER TABLE rules MODIFY inhibited_by JSON NOT NULL")
    op.execute(
        "ALTER TABLE notifications_log MODIFY suppressed_reason "
        f"ENUM({_ENUM_NEW}) NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE notifications_log SET suppressed_reason = NULL "
        "WHERE suppressed_reason = 'inhibited'"
    )
    op.execute(
        "ALTER TABLE notifications_log MODIFY suppressed_reason "
        f"ENUM({_ENUM_OLD}) NULL"
    )
    op.drop_column("rules", "inhibited_by")
