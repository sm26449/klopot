"""Every retention delete has an index to range over, and the model names
indexes as the migrations do (review K27).

Retention runs hourly in one transaction; on MySQL a DELETE without a usable
index scans — and locks — every row of the table until it commits, blocking
sign-ins (login_attempts), session checks (admin_sessions) and provider
callbacks (inbound_events) meanwhile.
"""
from __future__ import annotations

import pytest

from app.db.models import Base

# (table, column) each retention DELETE filters by range.
RETENTION_RANGES = [
    ("login_attempts", "ts"),
    ("admin_sessions", "last_seen_at"),
    ("inbound_events", "received_at"),
    ("api_requests", "expires_at"),
    ("delivery_attempts", "started_at"),
    ("system_events", "ts"),
    ("audit_log", "ts"),
    ("dedup_claims", "claimed_at"),
    ("schedule_occurrences", "scheduled_at"),
    ("channel_events", "created_at"),
]


@pytest.mark.parametrize(("table", "column"), RETENTION_RANGES)
def test_a_retention_range_leads_an_index(table, column):
    indexes = Base.metadata.tables[table].indexes
    assert any(next(iter(ix.columns)).name == column for ix in indexes), f"{table}.{column}"


def test_the_source_key_index_has_the_migration_name():
    names = {ix.name for ix in Base.metadata.tables["incidents"].indexes}
    assert "ix_incident_source_key" in names
    assert "ix_incidents_source_key" not in names
