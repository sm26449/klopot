"""Shared admission-claim protocol for fire dedup (audit R01, V04).

A non-test fire claims its ``(type, is_test=False, context_hash)`` slot so two
simultaneous identical fires resolve to a single winner. The claim is released
when the notification reaches a terminal state that must NOT coalesce future
fires — a full failure — so an identical fire can mint a fresh notification
instead of coalescing onto the dead one.

Both the dispatcher's synchronous path and the retry worker's terminal-failure
path use these helpers, so the claim lifecycle is one protocol rather than two
(the worker previously had no way to release a claim it failed terminally,
which is audit V04).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, false, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DedupClaim


async def claim_fire(
    session: AsyncSession, type_: str, context_hash: str,
    notif_id: str, now: datetime, cutoff: datetime,
) -> str:
    """Atomically claim the admission slot for a ``(type, context)`` fire.

    Returns the notification_id that holds the claim: ``notif_id`` when this
    fire won, or the concurrent winner's id. The upsert overwrites an existing
    claim only when it is stale (``claimed_at < cutoff``), so two simultaneous
    identical fires resolve to a single winner (audit R01). Claims are
    non-test only; the is_test column is always False here.
    """
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    values = {
        "type": type_, "is_test": False, "context_hash": context_hash,
        "notification_id": notif_id, "claimed_at": now,
    }
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(DedupClaim).values(**values).on_conflict_do_update(
            index_elements=["type", "is_test", "context_hash"],
            set_={"notification_id": notif_id, "claimed_at": now},
            where=DedupClaim.claimed_at < cutoff,
        )
    else:
        from sqlalchemy import case
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        stmt = mysql_insert(DedupClaim).values(**values)
        stmt = stmt.on_duplicate_key_update(
            notification_id=case(
                (DedupClaim.claimed_at < cutoff, stmt.inserted.notification_id),
                else_=DedupClaim.notification_id,
            ),
            claimed_at=case(
                (DedupClaim.claimed_at < cutoff, stmt.inserted.claimed_at),
                else_=DedupClaim.claimed_at,
            ),
        )
    await session.execute(stmt)

    # Read the winning claim back with a CURRENT read, not a snapshot read. The
    # loser of a true race upserts into a row the winner committed AFTER this
    # transaction's MySQL REPEATABLE-READ snapshot was taken; a plain SELECT
    # would miss it and raise NoResultFound (a rare concurrent-fire 500). FOR
    # UPDATE reads the latest committed row (the winner already released its
    # lock). SQLite has no row locks and serialises writers, so it renders no
    # FOR UPDATE there and is unaffected.
    #
    # ``is_test = false``, never ``IS false``: MySQL does not treat ``IS`` as a
    # key equality, so the lookup stops being a primary-key point read, scans
    # every claim of the type and FOR UPDATE locks them all — concurrent fires
    # of one type then deadlock (1213) and the loser's alert is rolled back.
    sel = select(DedupClaim.notification_id).where(
        DedupClaim.type == type_,
        DedupClaim.is_test == false(),
        DedupClaim.context_hash == context_hash,
    )
    if dialect != "sqlite":
        sel = sel.with_for_update()
    return (await session.execute(sel)).scalar_one()


async def release_claim(
    session: AsyncSession, type_: str, context_hash: str, notif_id: str,
) -> None:
    """Delete this fire's admission claim (only if it still holds it), so an
    identical retry of a terminally-failed fire isn't coalesced onto it
    (audit R01 × A02/A03, V04)."""
    await session.execute(
        delete(DedupClaim).where(
            DedupClaim.type == type_,
            DedupClaim.is_test == false(),
            DedupClaim.context_hash == context_hash,
            DedupClaim.notification_id == notif_id,
        )
    )
