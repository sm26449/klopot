"""One-off: mask literal secrets inside historical ``audit_log`` rows.

Before 2026-11-07 (audit C-2) ``model_to_dict`` masked only
``key_hash``, so every create/update of an input or channel copied its
full ``config`` — including the MQTT broker password and webhook
tokens stored literally — into ``audit_log.before`` / ``after``.
New rows are masked at write time; this script rewrites the old ones
through the same registry (``app/secrets_registry.py``).

Idempotent: a row whose snapshots are already masked is left alone.
Dry-run by default — pass ``--apply`` to write.

    docker compose exec alertd python -m scripts.scrub_audit_secrets           # report only
    docker compose exec alertd python -m scripts.scrub_audit_secrets --apply   # rewrite

Take a backup first (``scripts/backup.sh``); the script does not.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.db import dispose_engine, init_engine
from app.db.models import AuditLog
from app.secrets_registry import mask_config

logger = logging.getLogger("scrub_audit_secrets")

_RESOURCES = {"input", "channel"}


def _scrub_snapshot(resource: str, snap: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool]:
    """Return (new_snapshot, changed)."""
    if not isinstance(snap, dict) or not isinstance(snap.get("config"), dict):
        return snap, False
    masked = mask_config(resource, snap.get("kind"), snap["config"])
    if masked == snap["config"]:
        return snap, False
    return {**snap, "config": masked}, True


async def scrub(apply: bool) -> dict[str, int]:
    init_engine()
    from app.db.session import _session_factory as factory

    if factory is None:
        raise RuntimeError("Session factory not initialized")

    counts = {"scanned": 0, "changed": 0}
    async with factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.resource_kind.in_(_RESOURCES))
            )
        ).scalars().all()
        for row in rows:
            counts["scanned"] += 1
            resource = row.resource_kind or ""
            before, ch_b = _scrub_snapshot(resource, row.before)
            after, ch_a = _scrub_snapshot(resource, row.after)
            if ch_b or ch_a:
                counts["changed"] += 1
                logger.info(
                    "audit_log id=%s action=%s — %s",
                    row.id, row.action, "rewritten" if apply else "would rewrite",
                )
                if apply:
                    row.before = before
                    row.after = after
        if apply:
            await session.commit()
        else:
            await session.rollback()
    return counts


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    counts = await scrub(apply=args.apply)
    logger.info(
        "%s: scanned=%d changed=%d",
        "APPLIED" if args.apply else "DRY-RUN", counts["scanned"], counts["changed"],
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
