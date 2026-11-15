"""notifications_log_utc_migration

``notifications_log.fired_at`` was stored as server-local time: none
of the three NotificationLog creation sites in the dispatcher passed
``fired_at``, so MySQL's ``CURRENT_TIMESTAMP`` default (session
``time_zone=SYSTEM`` = Europe/Bucharest) filled it. Migration 0004's
docstring believed fired_at was already UTC — it never was.

Consequences before this fix (discovered 2026-07-06 by the restore
drill's report notification being silently deduped):

- The idempotency window compared local-time rows against a
  ``utc_now()`` cutoff, so identical fires were deduplicated for
  UTC-offset + window (~3h05m in summer) instead of 5 minutes.
- ``GET /v1/log?from/to`` filters and the retention sweep were
  skewed by the same offset.
- The API serializes fired_at with a ``Z`` suffix, so clients
  (pv-stack-ui ``fmtTime()`` converts UTC→local) displayed times
  +3h off.

v1.4.1 standardises fired_at on UTC at rest (same treatment 0004
gave ``audit_log.ts``):

- Dispatcher now passes ``fired_at=utc_now()`` explicitly at all
  three creation sites.
- This migration converts existing rows local → naive UTC using the
  server's current UTC offset. All existing rows (May 10 → Jul 6,
  2026) were written under EEST (+03:00), so a single offset is
  correct. Same caveat as 0004: NOT idempotent, and assumes the
  migration host shares the timezone that wrote the rows (the home
  deployment never moves).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-06 20:30:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    offset_s = conn.execute(sa.text(
        "SELECT UNIX_TIMESTAMP(NOW()) - UNIX_TIMESTAMP(UTC_TIMESTAMP())"
    )).scalar() or 0
    if offset_s == 0:
        # Server runs UTC (e.g. SQLite test DB / CI): rows are already
        # consistent with the new code path.
        return
    conn.execute(sa.text(
        "UPDATE notifications_log "
        "SET fired_at = fired_at - INTERVAL :offset SECOND"
    ), {"offset": offset_s})


def downgrade() -> None:
    conn = op.get_bind()
    offset_s = conn.execute(sa.text(
        "SELECT UNIX_TIMESTAMP(NOW()) - UNIX_TIMESTAMP(UTC_TIMESTAMP())"
    )).scalar() or 0
    if offset_s == 0:
        return
    conn.execute(sa.text(
        "UPDATE notifications_log "
        "SET fired_at = fired_at + INTERVAL :offset SECOND"
    ), {"offset": offset_s})
