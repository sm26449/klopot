"""widen_identifier_columns

Audit F25/F26: valid external names overflowed narrow identifier columns
on MySQL (error 1406/1452 → 500), because:

* ``audit_log.resource_id`` was VARCHAR(64) but a variable name may be up
  to 128 chars — a CREATE wrote the full name and the commit failed.
* ``notifications_log.source`` was VARCHAR(64) but a ``schedule:<name>``
  (and ``test:<name>``) origin can exceed 64 chars for a valid name, so
  no notification was durably enqueued.

Widen both to 191 (the utf8mb4 index-safe limit; ``resource_id`` is part
of the composite ``ix_audit_resource`` index). Additive and reversible.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-08 18:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "audit_log", "resource_id",
        existing_type=sa.String(64), type_=sa.String(191),
        existing_nullable=True,
    )
    op.alter_column(
        "notifications_log", "source",
        existing_type=sa.String(64), type_=sa.String(191),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "notifications_log", "source",
        existing_type=sa.String(191), type_=sa.String(64),
        existing_nullable=True,
    )
    op.alter_column(
        "audit_log", "resource_id",
        existing_type=sa.String(191), type_=sa.String(64),
        existing_nullable=True,
    )
