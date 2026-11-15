"""delivery_lease

Audit F04: a delivery claim/lease so the background worker cannot re-send a
delivery whose first (synchronous) attempt is still in flight. The dispatcher
leases each row for its sync attempt window; the worker only picks up rows
whose lease is absent or expired, and leases a row before its own retry. A
grace period alone is not ownership.

Additive and reversible. Existing rows get a NULL lease (claimable).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-08 20:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deliveries", sa.Column("lease_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("deliveries", "lease_until")
