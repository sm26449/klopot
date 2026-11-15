"""Indexes for the retention deletes (review K27).

Retention runs hourly in one transaction. On MySQL a DELETE without a usable
index scans every row of the table and locks each one it scans until the
transaction commits — blocking sign-ins (``login_attempts``), session checks
(``admin_sessions``) and provider callbacks (``inbound_events``) meanwhile.

Revision ID: 0039
Revises: 0038
"""
from __future__ import annotations

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_login_attempts_ts", "login_attempts", ["ts"]),
    ("ix_sessions_last_seen", "admin_sessions", ["last_seen_at"]),
    ("ix_inbound_events_received", "inbound_events", ["received_at"]),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in _INDEXES:
        op.drop_index(name, table_name=table)
