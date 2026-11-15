"""Push devices: who paused them (review K11).

``push_subscriptions.paused_reason`` is ``service`` (the service paused the
device after 20 refusals in a row) or ``operator``; NULL while enabled.
5603369 inferred it from ``enabled = false AND consecutive_failures >= 20``,
which a re-registration or an operator keeping the device paused got wrong.
Existing paused rows are classified by that same rule, once.

Revision ID: 0037
Revises: 0036
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("push_subscriptions", sa.Column("paused_reason", sa.String(16), nullable=True))
    op.execute(
        "UPDATE push_subscriptions SET paused_reason = CASE "
        "WHEN consecutive_failures >= 20 THEN 'service' ELSE 'operator' END "
        "WHERE enabled = 0"
    )


def downgrade() -> None:
    op.drop_column("push_subscriptions", "paused_reason")
