"""Episode keys compared byte for byte (review K01).

``incidents.source_key`` / ``active_source_key`` inherited the server
collation ``utf8mb4_unicode_ci``, which ignores case and accents: the
``idempotency_key`` values ``DiskFull`` and ``diskfull`` were one episode, so
the second firing sent nothing and a resolution of one closed the other.
``utf8mb4_bin`` makes them two. Binary comparison is stricter, so the existing
unique values stay unique and the index rebuild cannot fail. SQLite already
compares bytes — nothing to do there.

Revision ID: 0036
Revises: 0035
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

_COLUMNS = ("source_key", "active_source_key")


def _set_collation(collation: str) -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    for column in _COLUMNS:
        op.alter_column(
            "incidents", column,
            type_=mysql.VARCHAR(191, charset="utf8mb4", collation=collation),
            existing_type=sa.String(191), existing_nullable=True,
        )


def upgrade() -> None:
    _set_collation("utf8mb4_bin")


def downgrade() -> None:
    _set_collation("utf8mb4_unicode_ci")
