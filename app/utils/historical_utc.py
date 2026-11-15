"""Corrective re-normalisation for the flat-offset UTC migrations (audit R09).

Migrations 0004 (``audit_log.ts``) and 0005 (``notifications_log.fired_at``)
converted naive *server-local* timestamps to naive UTC by subtracting a SINGLE
offset — the migration host's UTC offset at the moment the migration ran. That
is correct only for rows whose original local time shared that same offset. A
row written in a different DST season (for Europe/Bucharest, a winter row when
the migration ran in summer) was shifted by the wrong amount and is now off by
the DST delta (one hour).

This module recomputes the correct UTC per row: it undoes the flat offset to
recover the original local wall-clock time, then re-normalises that wall time
with the zone's *historical* offset for that exact instant (DST-aware). Rows
whose historical offset already equals the applied offset are returned
unchanged, so running the correction over an already-correct table is a no-op.

Only rows that existed **when the migration ran** were flat-offset converted.
Rows written afterwards by the normal app are already correct naive UTC
(``utc_now()``), so the table is a mix and the correction must be bounded to
the pre-migration rows by a ``cutoff`` (the migration's run time) — applying it
to a post-migration row would wrongly shift a correct value by the DST delta.

The published migrations are not touched (the project is forward-only); the
companion CLI ``scripts/correct_historical_utc.py`` applies this as a one-off,
dry-run-first, and records a marker so it cannot be applied twice.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def zone_offset_at(tz: ZoneInfo, local_naive: datetime, *, fold: int = 0) -> timedelta:
    """The zone's UTC offset for a wall-clock instant (DST-aware).

    ``local_naive`` is interpreted as wall-clock time in ``tz``. ``fold``
    disambiguates the one repeated hour at a fall-back transition (0 = the
    first, earlier occurrence); it has no effect outside that hour.
    """
    return local_naive.replace(tzinfo=tz, fold=fold).utcoffset() or timedelta(0)


def correct_utc(
    stored_utc: datetime,
    applied_offset: timedelta,
    tz: ZoneInfo,
    *,
    fold: int = 0,
) -> datetime:
    """DST-correct naive UTC for a row the flat-offset migration wrote.

    ``stored_utc`` is what the migration left in the column — the original
    local time minus the single ``applied_offset``. Add the offset back to
    recover the original local wall time, then re-normalise it with the zone's
    historical offset for that instant. Returns a naive UTC datetime; equals
    ``stored_utc`` exactly when the historical offset matches ``applied_offset``.
    """
    local_naive = stored_utc + applied_offset
    historical = zone_offset_at(tz, local_naive, fold=fold)
    return local_naive - historical


def plan_corrections(
    rows: Iterable[tuple[object, datetime | None]],
    applied_offset: timedelta,
    tz: ZoneInfo,
    *,
    fold: int = 0,
    cutoff: datetime | None = None,
) -> list[tuple[object, datetime, datetime, timedelta]]:
    """Return ``(id, old, new, delta)`` for every row whose UTC value changes.

    ``rows`` is an iterable of ``(id, stored_utc)``. Rows are skipped when the
    value is NULL, when ``cutoff`` is set and the value is at or after it (those
    were written after the migration and are already correct native UTC, so they
    must never be shifted), or when the corrected value equals the stored one.
    The result is exactly the set of rows an apply pass would UPDATE. Pure — no
    I/O.
    """
    out: list[tuple[object, datetime, datetime, timedelta]] = []
    for rid, old in rows:
        if old is None:
            continue
        if cutoff is not None and old >= cutoff:
            continue
        new = correct_utc(old, applied_offset, tz, fold=fold)
        if new != old:
            out.append((rid, old, new, new - old))
    return out
