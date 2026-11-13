"""Timezone helpers.

`datetime.utcnow()` is deprecated in Python 3.12 and slated for removal.
The replacement `datetime.now(timezone.utc)` returns a tz-aware value,
which would break comparisons against naive `DateTime` columns loaded
from MySQL. `utc_now()` keeps the legacy naive-UTC semantics so call
sites and stored values stay consistent.
"""
from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return current UTC instant as a naive datetime (tzinfo stripped).

    Drop-in replacement for the deprecated `datetime.utcnow()`.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize an accepted instant to naive-UTC for the DB boundary
    (audit F15): an aware value is converted to UTC and stripped; a naive
    value is assumed to already be UTC. Without this, an offset-bearing
    input (e.g. ``02:00+02:00``) was stored as naive wall-clock ``02:00``
    instead of UTC ``00:00``, shifting snooze/expiry windows by the offset.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt
