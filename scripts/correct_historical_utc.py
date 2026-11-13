"""Correct the flat-offset UTC migrations 0004/0005 per-row (audit R09).

Migrations 0004 (``audit_log.ts``) and 0005 (``notifications_log.fired_at``)
normalised naive server-local timestamps to UTC by subtracting a SINGLE offset:
the migration host's UTC offset when it ran. Rows written in a different DST
season than the migration ran are therefore off by the DST delta. This tool
recomputes the correct UTC per row (``app.utils.historical_utc``) using the
deployment's timezone and the zone's historical offset for each row's instant.

It is a one-off corrective tool, NOT an automatic migration — the published
migrations stay untouched (the project is forward-only), and most deployments
need nothing. Safe by construction:

- **Dry-run by default.** It only reports what would change until you pass
  ``--apply``.
- **Single-apply.** An apply writes an ``audit_log`` marker and refuses to run
  again unless ``--force`` — re-applying would shift already-corrected rows.

Usage::

    # inspect (no writes)
    docker compose exec alertd python -m scripts.correct_historical_utc

    # apply, assuming the default home deployment
    docker compose exec alertd python -m scripts.correct_historical_utc --apply

    # a migration that ran on a different host/season than the default guess
    python -m scripts.correct_historical_utc --applied-offset +02:00 --apply

The timezone defaults to ``settings.timezone`` (the deployment's own recorded
zone); the applied offset defaults, per table, to that zone's offset on the
migration's date — the normal case where the migration ran promptly on the home
host. Override ``--applied-offset`` when you know it ran elsewhere/off-season.
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
from app.db.models import ActorKind, AuditLog, Settings
from app.utils.historical_utc import plan_corrections, zone_offset_at
from app.utils.time import utc_now

logger = logging.getLogger("correct_historical_utc")

MARKER_ACTION = "historical_utc_corrected"


@dataclass(frozen=True)
class TableSpec:
    table: str
    column: str
    migrated_on: datetime  # when the migration ran: default-offset season AND the cutoff


# The two columns the flat-offset migrations touched, with each migration's run
# time (its Create Date). That time is used twice: the default applied offset is
# the zone's offset in that season, and it is the cutoff — only rows written
# BEFORE it were flat-offset converted; rows written after are already correct
# native UTC and must not be shifted (the table is a mix of both).
TABLES = [
    TableSpec("audit_log", "ts", datetime(2026, 5, 17, 12, 30)),
    TableSpec("notifications_log", "fired_at", datetime(2026, 7, 6, 20, 30)),
]


def parse_offset(spec: str) -> timedelta:
    """Parse ``+HH:MM`` / ``-HH:MM`` / ``HH`` into a timedelta."""
    s = spec.strip()
    sign = 1
    if s.startswith("+"):
        s = s[1:]
    elif s.startswith("-"):
        sign = -1
        s = s[1:]
    hours, _, minutes = s.partition(":")
    return sign * timedelta(hours=int(hours), minutes=int(minutes or 0))


async def _already_applied(session) -> bool:
    n = (
        await session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == MARKER_ACTION)
        )
    ).scalar_one()
    return bool(n)


async def run(
    *,
    apply: bool,
    tz_name: str | None,
    applied_offset_override: timedelta | None,
    force: bool,
) -> int:
    """Return the number of rows that were (or would be) corrected."""
    init_engine()
    from app.db.session import _session_factory as factory  # initialised by init_engine

    if factory is None:
        raise RuntimeError("Session factory not initialized")

    async with factory() as session:
        # Resolve the timezone: explicit flag wins, else the deployment's own.
        if not tz_name:
            tz_name = (
                await session.execute(select(Settings.timezone).where(Settings.id == 1))
            ).scalar_one_or_none() or "UTC"
        tz = ZoneInfo(tz_name)
        logger.info("timezone: %s", tz_name)

        if apply and not force and await _already_applied(session):
            logger.error(
                "Refusing to apply: an '%s' marker already exists in audit_log. "
                "The correction has run before; re-applying would shift corrected "
                "rows again. Pass --force only if you are certain it is needed.",
                MARKER_ACTION,
            )
            return 0

        total_changed = 0
        summary: dict[str, int] = {}
        for spec in TABLES:
            applied = (
                applied_offset_override
                if applied_offset_override is not None
                else zone_offset_at(tz, spec.migrated_on)
            )
            # Only pre-migration rows were flat-offset converted; rows written
            # after the migration are already native UTC. Bound by the cutoff in
            # SQL (and again in plan_corrections as a safety belt).
            rows = (
                await session.execute(
                    text(f"SELECT id, {spec.column} FROM {spec.table} WHERE {spec.column} < :cutoff"),
                    {"cutoff": spec.migrated_on},
                )
            ).all()
            plan = plan_corrections(
                ((r[0], r[1]) for r in rows), applied, tz, cutoff=spec.migrated_on
            )
            summary[spec.table] = len(plan)
            total_changed += len(plan)
            logger.info(
                "%s.%s: %d of %d pre-migration row(s) need correction "
                "(applied offset %s, cutoff %s)",
                spec.table, spec.column, len(plan), len(rows),
                _fmt_offset(applied), spec.migrated_on.isoformat(sep=" "),
            )
            for rid, old, new, delta in plan[:5]:
                logger.info("  id=%s  %s -> %s  (%+d min)", rid, old, new, int(delta.total_seconds() // 60))
            if len(plan) > 5:
                logger.info("  … and %d more", len(plan) - 5)

            if apply and plan:
                upd = text(f"UPDATE {spec.table} SET {spec.column} = :new WHERE id = :id")
                for rid, _old, new, _delta in plan:
                    await session.execute(upd, {"new": new, "id": rid})

        if apply:
            session.add(
                AuditLog(
                    ts=utc_now(),
                    actor_kind=ActorKind.system,
                    actor_name="correct_historical_utc",
                    action=MARKER_ACTION,
                    resource_kind="maintenance",
                    resource_id="0004_0005",
                    after={"timezone": tz_name, "corrected": summary},
                )
            )
            await session.commit()
            logger.info("Applied: corrected %d row(s); marker written.", total_changed)
        else:
            logger.info(
                "Dry run: %d row(s) would be corrected. Re-run with --apply to write.",
                total_changed,
            )
    await dispose_engine()
    return total_changed


def _fmt_offset(td: timedelta) -> str:
    total = int(td.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Correct 0004/0005 flat-offset UTC rows (audit R09).")
    p.add_argument("--apply", action="store_true", help="Write the corrections (default: dry run).")
    p.add_argument("--timezone", default=None, help="Original zone (default: settings.timezone).")
    p.add_argument(
        "--applied-offset",
        default=None,
        help="Offset the migration subtracted, e.g. +03:00 (default: the zone's "
        "offset on each migration's date).",
    )
    p.add_argument("--force", action="store_true", help="Apply again despite an existing marker.")
    return p.parse_args(argv)


async def _main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args(argv)
    override = parse_offset(args.applied_offset) if args.applied_offset else None
    await run(
        apply=args.apply,
        tz_name=args.timezone,
        applied_offset_override=override,
        force=args.force,
    )


if __name__ == "__main__":
    asyncio.run(_main())
