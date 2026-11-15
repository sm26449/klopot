"""Read-only legacy-UTC preflight (audit B-09).

Historical timestamps in a **populated legacy upgrade** can be wrong:

  * ``audit_log.ts`` / ``notifications_log.fired_at`` — migrations 0004/0005
    subtracted a SINGLE current offset from every pre-migration row, which is
    correct only for rows written in the same DST season the migration ran in
    (see ``scripts/correct_historical_utc.py``, audit R09).
  * config-row ``created_at`` / ``updated_at`` — stored as container-local time
    before the session-UTC fix (see ``scripts/correct_config_timestamps_b13.py``,
    audit B-13).

A **fresh install is unaffected** by either. This tool tells an operator, before
or after upgrading a populated database, whether a repair is needed — without
writing anything. It reuses the two repair tools' own definitions and their
pure ``plan_corrections`` dry-run, so its verdict matches exactly what an
``--apply`` run would change. See ``docs/LEGACY_UTC.md`` for the full policy.

Exit codes:
  * ``0`` — no action needed (a correction marker is present, or zero suspect
    rows), for every domain that was assessed.
  * ``2`` — at least one domain has suspect rows and no correction marker: run
    the corresponding repair tool.

The config domain needs the session-UTC deploy instant to assess (rows at or
after it are already UTC); pass it as ``--config-cutoff``. Without it, the config
domain is reported as *not assessed* and does not affect the exit code.

Usage::

    docker compose exec alertd python -m scripts.check_legacy_utc \
        --config-cutoff 2026-11-12T05:00:00
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text

from app.db import dispose_engine, init_engine
from app.db.models import AuditLog, Settings
from app.utils.historical_utc import plan_corrections, zone_offset_at
from scripts.correct_config_timestamps_b13 import (
    MARKER_ACTION as B13_MARKER,
)
from scripts.correct_config_timestamps_b13 import (
    parse_cutoff,
    target_columns,
)
from scripts.correct_historical_utc import (
    MARKER_ACTION as R09_MARKER,
)
from scripts.correct_historical_utc import (
    TABLES as R09_TABLES,
)

logger = logging.getLogger("check_legacy_utc")


@dataclass(frozen=True)
class DomainResult:
    """One assessed domain. ``suspect`` is the count of rows a repair would
    change; ``assessed`` is False when we lacked an input to judge it;
    ``marked`` is True when a correction marker already exists."""

    label: str
    assessed: bool
    marked: bool
    suspect: int


def decide_exit(results: list[DomainResult]) -> int:
    """Exit 2 iff some assessed, unmarked domain has suspect rows."""
    needs_action = any(
        r.assessed and not r.marked and r.suspect > 0 for r in results
    )
    return 2 if needs_action else 0


async def _marker_exists(session, action: str) -> bool:
    n = (
        await session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()
    return bool(n)


async def run(*, tz_name: str | None, config_cutoff: datetime | None) -> int:
    """Assess both domains read-only and return the process exit code."""
    init_engine()
    from app.db.session import _session_factory as factory  # set by init_engine

    if factory is None:
        raise RuntimeError("Session factory not initialized")

    results: list[DomainResult] = []
    async with factory() as session:
        if not tz_name:
            tz_name = (
                await session.execute(select(Settings.timezone).where(Settings.id == 1))
            ).scalar_one_or_none() or "UTC"
        tz = ZoneInfo(tz_name)
        logger.info("source timezone: %s", tz_name)

        # ── R09 domain: audit_log.ts / notifications_log.fired_at ──
        r09_marked = await _marker_exists(session, R09_MARKER)
        for spec in R09_TABLES:
            if r09_marked:
                results.append(DomainResult(f"{spec.table}.{spec.column}", True, True, 0))
                logger.info("%s.%s: already corrected (R09 marker present)", spec.table, spec.column)
                continue
            applied = zone_offset_at(tz, spec.migrated_on)
            rows = (
                await session.execute(
                    text(f"SELECT id, {spec.column} FROM {spec.table} WHERE {spec.column} < :c"),
                    {"c": spec.migrated_on},
                )
            ).all()
            plan = plan_corrections(((r[0], r[1]) for r in rows), applied, tz, cutoff=spec.migrated_on)
            results.append(DomainResult(f"{spec.table}.{spec.column}", True, False, len(plan)))
            logger.info(
                "%s.%s: %d of %d pre-migration row(s) are offset-suspect",
                spec.table, spec.column, len(plan), len(rows),
            )

        # ── B-13 domain: config-row created_at / updated_at ──
        b13_marked = await _marker_exists(session, B13_MARKER)
        if b13_marked:
            results.append(DomainResult("config timestamps", True, True, 0))
            logger.info("config timestamps: already corrected (B-13 marker present)")
        elif config_cutoff is None:
            results.append(DomainResult("config timestamps", False, False, 0))
            logger.info(
                "config timestamps: NOT ASSESSED — pass --config-cutoff "
                "(the session-UTC deploy instant) to assess this domain."
            )
        else:
            total = 0
            for table, col in target_columns():
                pk_cols = list(table.primary_key.columns)
                rows = (
                    await session.execute(
                        select(*pk_cols, col).where(col < config_cutoff).where(col.is_not(None))
                    )
                ).all()
                keyed = [(tuple(r[: len(pk_cols)]), r[-1]) for r in rows]
                total += len(plan_corrections(keyed, timedelta(0), tz, cutoff=config_cutoff))
            results.append(DomainResult("config timestamps", True, False, total))
            logger.info("config timestamps: %d row(s) before cutoff are offset-suspect", total)

    await dispose_engine()

    code = decide_exit(results)
    if code == 0:
        logger.info("Preflight OK: no legacy-UTC correction needed for the assessed domains.")
    else:
        logger.warning(
            "ACTION NEEDED: run scripts.correct_historical_utc and/or "
            "scripts.correct_config_timestamps_b13 (see docs/LEGACY_UTC.md)."
        )
    return code


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only legacy-UTC preflight (audit B-09).")
    p.add_argument("--timezone", default=None, help="Source zone (default: settings.timezone).")
    p.add_argument(
        "--config-cutoff",
        default=None,
        help="UTC ISO instant the session-UTC fix deployed; enables the config "
        "domain assessment (e.g. 2026-11-12T05:00:00).",
    )
    return p.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args(argv)
    cutoff = parse_cutoff(args.config_cutoff) if args.config_cutoff else None
    return await run(tz_name=args.timezone, config_cutoff=cutoff)


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(_main()))
