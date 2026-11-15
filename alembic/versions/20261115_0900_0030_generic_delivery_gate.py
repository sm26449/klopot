"""Generic delivery gate: templates.gate_variable + gate_min replace
require_pv_kw; suppressed reason pv_power → below_gate.

Before: every template's ``require_pv_kw`` compared against ONE global
variable named by ``ALERTD_PV_POWER_VAR`` — solar-specific in name and
unusable for anything else. Now each template names its own variable and
threshold. Existing rows are converted: ``gate_min = require_pv_kw`` and,
when ``ALERTD_PV_POWER_VAR`` is set in the environment running the
migration, ``gate_variable`` = that name (unset → no variable, which is
exactly the old behaviour: the gate had no effect).

Revision ID: 0030
Revises: 0029
"""
from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_BASE = "'disabled','snoozed','throttled','persist','gated','duplicate','unknown_type','inhibited'"


def _reason_enum(values: str) -> None:
    op.execute(f"ALTER TABLE notifications_log MODIFY suppressed_reason ENUM({values}) NULL")


def upgrade() -> None:
    op.add_column("templates", sa.Column("gate_variable", sa.String(128), nullable=True))
    op.add_column("templates", sa.Column("gate_min", sa.Float(), nullable=True))
    legacy_var = os.environ.get("ALERTD_PV_POWER_VAR", "").strip() or None
    op.execute(
        sa.text(
            "UPDATE templates SET gate_min = require_pv_kw, gate_variable = :var "
            "WHERE require_pv_kw IS NOT NULL"
        ).bindparams(var=legacy_var)
    )
    op.drop_column("templates", "require_pv_kw")

    # Widen, move the rows, narrow — MySQL rejects an ENUM change that would
    # orphan existing values.
    _reason_enum(f"{_BASE},'pv_power','below_gate'")
    op.execute("UPDATE notifications_log SET suppressed_reason = 'below_gate' WHERE suppressed_reason = 'pv_power'")
    _reason_enum(f"{_BASE},'below_gate'")


def downgrade() -> None:
    _reason_enum(f"{_BASE},'pv_power','below_gate'")
    op.execute("UPDATE notifications_log SET suppressed_reason = 'pv_power' WHERE suppressed_reason = 'below_gate'")
    _reason_enum(f"{_BASE},'pv_power'")

    op.add_column("templates", sa.Column("require_pv_kw", sa.Float(), nullable=True))
    op.execute("UPDATE templates SET require_pv_kw = gate_min WHERE gate_min IS NOT NULL")
    op.drop_column("templates", "gate_min")
    op.drop_column("templates", "gate_variable")
