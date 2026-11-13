"""notification_delivery_status

Persist the settled delivery outcome of every fire (audit A03).

Before this, "was it delivered?" was inferred from
``suppressed_reason IS NULL`` — which is WRONG for a fire that reached
dispatch but had every channel fail (no suppression reason, yet nobody
was notified). That row was counted as dispatched in stats and replayed
as a phantom success by the idempotency check.

``notifications_log.delivery_status`` records the truth:
``sent | partial | failed | suppressed``. Additive and nullable so the
previous image keeps writing rows (they just read back as NULL until
re-derived); existing rows are backfilled here from the same rule the
application now applies at write time.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-08 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DELIVERY_STATUS = sa.Enum(
    "sent", "partial", "failed", "suppressed", name="deliverystatus"
)


def upgrade() -> None:
    op.add_column(
        "notifications_log",
        sa.Column("delivery_status", _DELIVERY_STATUS, nullable=True),
    )

    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        # Backfill existing rows with the same derivation the dispatcher
        # now applies. JSON_LENGTH([]) / JSON_LENGTH({}) == 0, so an
        # empty dispatched_to with a non-empty failed_channels (or both
        # empty) resolves to 'failed'.
        op.execute(
            """
            UPDATE notifications_log
            SET delivery_status = CASE
                WHEN suppressed_reason IS NOT NULL THEN 'suppressed'
                WHEN JSON_LENGTH(dispatched_to) > 0
                     AND JSON_LENGTH(failed_channels) > 0 THEN 'partial'
                WHEN JSON_LENGTH(dispatched_to) > 0 THEN 'sent'
                ELSE 'failed'
            END
            WHERE delivery_status IS NULL
            """
        )

    op.create_index(
        "ix_log_delivery_fired",
        "notifications_log",
        ["delivery_status", "fired_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_log_delivery_fired", table_name="notifications_log")
    op.drop_column("notifications_log", "delivery_status")
