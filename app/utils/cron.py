"""DST-safe cron occurrence computation.

``croniter`` interprets an expression against whatever anchor it is
given. When the anchor is a **timezone-aware** local datetime, croniter
3.x carries that anchor's fixed UTC offset forward across a DST
transition, so the civil firing time drifts: a ``03:30`` daily alert in
``Europe/Bucharest`` fires at ``04:30`` the day after the autumn
fall-back (B-08).

The correct pattern — documented by croniter itself — is to drive the
parser on **naive local wall time** and localize each result to the
target zone afterwards, so the configured civil time is preserved and
the UTC offset is recomputed for each occurrence's own date.

Both the firing runtime (``schedule_service``) and the editor preview
(``/v1/schedules/preview``) call through here, so a previewed time and
the time the schedule actually fires can never disagree.

Gap / fold policy (explicit):

  * **Ambiguous** fall-back wall times — a local time that occurs twice —
    resolve to the FIRST occurrence (the pre-transition offset,
    ``fold=0``). A ``03:30`` daily on fall-back day fires at the earlier
    ``03:30``.
  * **Nonexistent** spring-forward wall times — a local time skipped by
    the jump — resolve through the pre-transition offset, i.e. the
    equivalent real instant; the following day returns to the configured
    civil time.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter


def _iter_local(cron_expr: str, after_utc: datetime, tz: ZoneInfo) -> Iterator[datetime]:
    """Yield successive cron occurrences strictly after ``after_utc``,
    each as a tz-aware datetime in ``tz``.

    ``after_utc`` may be naive (assumed UTC) or aware. croniter runs on
    naive local wall time; each result is localized to ``tz`` with the
    gap/fold policy documented in the module docstring. Raises whatever
    croniter raises for an invalid expression, on the first ``next``.
    """
    if after_utc.tzinfo is None:
        after_utc = after_utc.replace(tzinfo=UTC)
    after_local_naive = after_utc.astimezone(tz).replace(tzinfo=None)
    it = croniter(cron_expr, after_local_naive)
    while True:
        nxt_naive: datetime = it.get_next(datetime)
        # Attach the target zone (fold=0) so the offset is recomputed for
        # this occurrence's own date rather than inherited from the anchor.
        yield nxt_naive.replace(tzinfo=tz)


def cron_next_utc(cron_expr: str, after_utc: datetime, tz: ZoneInfo) -> datetime:
    """Next cron occurrence strictly after ``after_utc``, as **naive UTC**.

    For storage in a naive-UTC ``DateTime`` column. See the module
    docstring for the DST gap/fold policy.
    """
    nxt = next(_iter_local(cron_expr, after_utc, tz))
    return nxt.astimezone(UTC).replace(tzinfo=None)


def cron_preview_local(
    cron_expr: str, after_utc: datetime, tz: ZoneInfo, count: int
) -> list[datetime]:
    """Next ``count`` occurrences strictly after ``after_utc``, each a
    tz-aware local datetime in ``tz``.

    For the schedule editor preview. Shares :func:`_iter_local` with the
    firing runtime so preview and firing agree across DST (B-08).
    """
    it = _iter_local(cron_expr, after_utc, tz)
    return [next(it) for _ in range(count)]
