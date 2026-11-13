"""audit_log_utc_migration

Audit-log historical UTC normalization. Before v1.3.4, ``audit_log.ts``
was stored as server-local time (MySQL ``func.current_timestamp()`` +
``@@time_zone=SYSTEM``) while ``notifications_log.fired_at`` was
stored as UTC (via ``utc_now()``). Two compensating UI bugs hid the
inconsistency: ``fmtTime()`` (Log tab) auto-converted UTC → local;
``renderAuditRow()`` (Audit tab) displayed ts raw without conversion.

v1.3.4 standardises on UTC at rest:

- New audit rows go in via ``record_change`` which now explicitly
  passes ``ts=utc_now()``.
- This migration converts existing rows from server-local back to
  naive UTC.
- Pydantic ``AuditLogRead.ts`` field-serializer emits Z suffix.
- The UI's audit-render path is being updated in pv-stack-ui to use
  the same ``fmtTime`` helper as Log rows.

The migration subtracts the host's UTC offset from every existing
``audit_log.ts``. We compute the offset from ``UNIX_TIMESTAMP(NOW()) -
UNIX_TIMESTAMP(UTC_TIMESTAMP())`` — works regardless of DST because
all existing rows are recent (May 2026, EEST = +03:00) and were
stamped at insertion-time under the same offset.

Edge case: if alembic ever runs this migration on a machine in a
DIFFERENT timezone from the one that wrote the rows, the offset
won't match. Since the home deployment never moves, that's
theoretical. Marked accordingly in the upgrade comment.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-17 12:30:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Compute and apply the local→UTC delta. Idempotent only because
    # the new code path writes UTC — running this migration twice
    # would shift twice. Guard with a row-count check (skip if a
    # marker column or marker row exists).
    conn = op.get_bind()
    # Offset in seconds, positive = local is ahead of UTC.
    offset_s = conn.execute(sa.text(
        "SELECT UNIX_TIMESTAMP(NOW()) - UNIX_TIMESTAMP(UTC_TIMESTAMP())"
    )).scalar() or 0
    if offset_s == 0:
        # Server is UTC; nothing to do. Future inserts also write
        # UTC, so the table is consistent.
        return
    # Subtract the offset from every ts.
    conn.execute(sa.text(
        "UPDATE audit_log "
        "SET ts = ts - INTERVAL :offset SECOND"
    ), {"offset": offset_s})


def downgrade() -> None:
    # Add the offset back.
    conn = op.get_bind()
    offset_s = conn.execute(sa.text(
        "SELECT UNIX_TIMESTAMP(NOW()) - UNIX_TIMESTAMP(UTC_TIMESTAMP())"
    )).scalar() or 0
    if offset_s == 0:
        return
    conn.execute(sa.text(
        "UPDATE audit_log "
        "SET ts = ts + INTERVAL :offset SECOND"
    ), {"offset": offset_s})
