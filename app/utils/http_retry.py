"""Reading an upstream's retry hints (``Retry-After``) and status classes."""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

# A Retry-After longer than this is treated as this (a delivery gives up after
# an hour anyway — outbox.MAX_DELIVERY_AGE_SEC).
MAX_RETRY_AFTER_SEC = 3600.0
# Statuses that mean "slow down / come back later", not "this failed".
BACKPRESSURE_STATUSES = frozenset({429, 503})


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Seconds to wait from a ``Retry-After`` header (delta-seconds or an
    HTTP-date), clamped to [1, MAX_RETRY_AFTER_SEC]; None if absent / invalid."""
    if not value:
        return None
    text = value.strip()
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or datetime.now(UTC))).total_seconds()
    if seconds != seconds:  # NaN
        return None
    return max(1.0, min(MAX_RETRY_AFTER_SEC, seconds))


def is_permanent_client_error(status: int) -> bool:
    """A 4xx a retry will not fix (bad request, auth, conflict…) — everything
    in 400–499 except 408 Request Timeout and 429 Too Many Requests."""
    return 400 <= status < 500 and status not in (408, 429)
