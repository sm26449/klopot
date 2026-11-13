"""suppressed_reason pv_power

Audit A34: ``Template.require_pv_kw`` now gates dispatch — a template's
alert is suppressed while the configured PV-power variable reads below
the threshold. The suppression stays visible in the log/digest under a
dedicated ``pv_power`` reason, which this migration adds to the
``notifications_log.suppressed_reason`` enum.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-08 12:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_OLD = (
    "'disabled','snoozed','throttled','persist','gated',"
    "'duplicate','unknown_type','inhibited'"
)
_ENUM_NEW = _ENUM_OLD + ",'pv_power'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE notifications_log MODIFY suppressed_reason "
        f"ENUM({_ENUM_NEW}) NULL"
    )


def downgrade() -> None:
    # Clear any rows using the new value before narrowing the enum back.
    op.execute(
        "UPDATE notifications_log SET suppressed_reason = NULL "
        "WHERE suppressed_reason = 'pv_power'"
    )
    op.execute(
        "ALTER TABLE notifications_log MODIFY suppressed_reason "
        f"ENUM({_ENUM_OLD}) NULL"
    )
