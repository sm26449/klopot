"""Correct config-row timestamps stored as container-local time (audit B-13).

Until the session-UTC enforcement in ``app/db/session.py`` shipped, the MySQL
session ran in the container's OS timezone (e.g. ``Europe/Bucharest``), so every
``CURRENT_TIMESTAMP`` server default wrote the **local wall-clock** time into a
naive ``DATETIME`` column. Those values are then served with a ``Z`` suffix, so
a row created at 09:00 UTC reads back as 11:00Z. The fix makes new writes UTC;
this one-off tool repairs the rows written before it.

It recomputes the correct UTC per row with the zone's *historical* offset for
each row's own instant (DST-aware) — reusing :mod:`app.utils.historical_utc`
with a zero applied offset, because the stored value is the original local time
itself (not local-minus-an-offset as in the R09 flat-offset case).

**Provenance (what is and isn't touched):**

- Swept: every config/entity ``CURRENT_TIMESTAMP`` column (``created_at`` /
  ``updated_at`` across the config tables), discovered from the ORM metadata.
- **Excluded**: ``audit_log.ts`` and ``notifications_log.fired_at`` — the
  already-UTC log fields that migrations 0004/0005 and the R09 tool own. The
  audit is explicit: do not shift already-UTC log/audit/session fields. Session
  rows are app-written UTC and carry no ``CURRENT_TIMESTAMP`` default, so they
  are never in scope.
- **Bounded by ``--cutoff``** (the UTC instant the session-UTC fix deployed):
  only rows whose value predates it were written in local time; rows at or after
  it are already native UTC and must never be shifted. The table is a mix, so
  the bound is applied per value — a row created before the fix but updated
  after it has its ``created_at`` repaired and its ``updated_at`` left alone.

Safe by construction, like the R09 tool:

- **Dry-run by default** — reports what would change until ``--apply``.
- **Single-apply** — an apply writes an ``audit_log`` marker and refuses to run
  again without ``--force``; re-applying would shift corrected rows twice.

Usage::

    # inspect (no writes); cutoff = when the session-UTC fix deployed
    docker compose exec alertd python -m scripts.correct_config_timestamps_b13 \
        --cutoff 2026-11-12T05:00:00

    # apply
    docker compose exec alertd python -m scripts.correct_config_timestamps_b13 \
        --cutoff 2026-11-12T05:00:00 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.schema import Column, Table

from app.db import dispose_engine, init_engine
from app.db.models import ActorKind, AuditLog, Base, Settings
from app.utils.historical_utc import plan_corrections
from app.utils.time import utc_now

logger = logging.getLogger("correct_config_timestamps_b13")

MARKER_ACTION = "config_timestamps_utc_corrected"

# Already-UTC log fields owned by migrations 0004/0005 + the R09 tool. Shifting
# them here would double-correct. Any NEW CURRENT_TIMESTAMP column that is a log
# field (not config) must be added here; the companion test cross-checks this
# set against the ORM metadata so an unclassified column fails loudly.
EXCLUDED: frozenset[tuple[str, str]] = frozenset(
    {("audit_log", "ts"), ("notifications_log", "fired_at")}
)


def _is_current_timestamp(col: Column) -> bool:
    sd = col.server_default
    return sd is not None and "current_timestamp" in str(sd.arg).lower()


def target_columns() -> list[tuple[Table, Column]]:
    """Every config ``CURRENT_TIMESTAMP`` column to repair, minus EXCLUDED.

    Derived from the ORM metadata so the set can't silently drift from the
    schema. Deterministic order for stable logging.
    """
    out: list[tuple[Table, Column]] = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if _is_current_timestamp(col) and (table.name, col.name) not in EXCLUDED:
                out.append((table, col))
    return out


def parse_cutoff(spec: str) -> datetime:
    """Parse a naive-UTC ISO cutoff; reject an offset-bearing value."""
    dt = datetime.fromisoformat(spec)
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return dt


async def apply_column_corrections(session, table: Table, pk_cols, col: Column, plan) -> None:
    """Write a column's corrected values with a **raw** per-row UPDATE.

    A Core ``update().values({col: new})`` would additionally apply this
    table's ``onupdate=CURRENT_TIMESTAMP`` to ``updated_at`` — clobbering a
    sibling timestamp we are trying to correct. The raw statement sets ONLY
    ``col``, so a sibling column is never touched by correcting this one.
    """
    pk_pred = " AND ".join(f"{c.name} = :pk{i}" for i, c in enumerate(pk_cols))
    stmt = text(f"UPDATE {table.name} SET {col.name} = :new WHERE {pk_pred}")
    for pk, _old, new, _delta in plan:
        params: dict[str, object] = {"new": new}
        params.update({f"pk{i}": v for i, v in enumerate(pk)})
        await session.execute(stmt, params)


async def _already_applied(session) -> bool:
    n = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == MARKER_ACTION)
        )
    ).scalar_one()
    return bool(n)


async def run(
    *,
    apply: bool,
    cutoff: datetime,
    tz_name: str | None,
    force: bool,
) -> int:
    """Return the number of rows that were (or would be) corrected."""
    init_engine()
    from app.db.session import _session_factory as factory  # set by init_engine

    if factory is None:
        raise RuntimeError("Session factory not initialized")

    async with factory() as session:
        if not tz_name:
            tz_name = (
                await session.execute(select(Settings.timezone).where(Settings.id == 1))
            ).scalar_one_or_none() or "UTC"
        tz = ZoneInfo(tz_name)
        logger.info("source timezone: %s | cutoff (UTC): %s", tz_name, cutoff.isoformat(sep=" "))

        if apply and not force and await _already_applied(session):
            logger.error(
                "Refusing to apply: a '%s' marker already exists in audit_log. "
                "The correction has run before; re-applying would shift corrected "
                "rows again. Pass --force only if you are certain.",
                MARKER_ACTION,
            )
            return 0

        total_changed = 0
        summary: dict[str, int] = {}
        for table, col in target_columns():
            pk_cols = list(table.primary_key.columns)
            sel = (
                select(*pk_cols, col)
                .where(col < cutoff)
                .where(col.is_not(None))
            )
            rows = (await session.execute(sel)).all()
            # Key each row by its PK tuple; the value is the last selected col.
            keyed = [(tuple(r[: len(pk_cols)]), r[-1]) for r in rows]
            plan = plan_corrections(keyed, timedelta(0), tz, cutoff=cutoff)
            key = f"{table.name}.{col.name}"
            summary[key] = len(plan)
            total_changed += len(plan)
            if plan:
                logger.info(
                    "%s: %d of %d pre-cutoff row(s) need correction", key, len(plan), len(rows)
                )
                for pk, old, new, delta in plan[:5]:
                    logger.info(
                        "  %s=%s  %s -> %s  (%+d min)",
                        [c.name for c in pk_cols], list(pk), old, new,
                        int(delta.total_seconds() // 60),
                    )
                if len(plan) > 5:
                    logger.info("  … and %d more", len(plan) - 5)

            if apply and plan:
                await apply_column_corrections(session, table, pk_cols, col, plan)

        if apply:
            session.add(
                AuditLog(
                    ts=utc_now(),
                    actor_kind=ActorKind.system,
                    actor_name="correct_config_timestamps_b13",
                    action=MARKER_ACTION,
                    resource_kind="maintenance",
                    resource_id="b13",
                    after={
                        "timezone": tz_name,
                        "cutoff": cutoff.isoformat(),
                        "corrected": summary,
                    },
                )
            )
            await session.commit()
            logger.info("Applied: corrected %d value(s); marker written.", total_changed)
        else:
            logger.info(
                "Dry run: %d value(s) would be corrected. Re-run with --apply to write.",
                total_changed,
            )
    await dispose_engine()
    return total_changed


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Correct config-row timestamps stored as local time (audit B-13)."
    )
    p.add_argument(
        "--cutoff",
        required=True,
        help="UTC ISO instant the session-UTC fix deployed; only rows BEFORE it "
        "are repaired (e.g. 2026-11-12T05:00:00).",
    )
    p.add_argument("--apply", action="store_true", help="Write the corrections (default: dry run).")
    p.add_argument("--timezone", default=None, help="Source zone (default: settings.timezone).")
    p.add_argument("--force", action="store_true", help="Apply again despite an existing marker.")
    return p.parse_args(argv)


async def _main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args(argv)
    await run(
        apply=args.apply,
        cutoff=parse_cutoff(args.cutoff),
        tz_name=args.timezone,
        force=args.force,
    )


if __name__ == "__main__":
    asyncio.run(_main())
