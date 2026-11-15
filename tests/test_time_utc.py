"""F15: instant normalization to naive-UTC at the DB boundary."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.utils.time import to_naive_utc


def test_aware_offset_converted_to_utc_and_stripped():
    # 02:00 at +02:00 is 00:00 UTC.
    dt = datetime(2030, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=2)))
    out = to_naive_utc(dt)
    assert out == datetime(2030, 1, 1, 0, 0)
    assert out.tzinfo is None


def test_negative_offset():
    dt = datetime(2030, 1, 1, 22, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert to_naive_utc(dt) == datetime(2030, 1, 2, 3, 0)


def test_naive_assumed_utc():
    dt = datetime(2030, 1, 1, 2, 0)
    assert to_naive_utc(dt) == dt


def test_none_passthrough():
    assert to_naive_utc(None) is None


def test_utc_aware():
    dt = datetime(2030, 1, 1, 2, 0, tzinfo=UTC)
    assert to_naive_utc(dt) == datetime(2030, 1, 1, 2, 0)
