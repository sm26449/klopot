"""B-13 historical repair tool (scripts.correct_config_timestamps_b13).

The tool targets exactly the config ``CURRENT_TIMESTAMP`` columns — never the
already-UTC log fields — and corrects a local wall-clock value to UTC
DST-correctly, bounded by the deploy cutoff.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.utils.historical_utc import plan_corrections
from scripts.correct_config_timestamps_b13 import (
    EXCLUDED,
    _is_current_timestamp,
    apply_column_corrections,
    parse_cutoff,
    target_columns,
)

BUCHAREST = ZoneInfo("Europe/Bucharest")


# ── Target set & provenance ──────────────────────────────────────────


def test_target_columns_exclude_already_utc_log_fields():
    names = {(t.name, c.name) for t, c in target_columns()}
    assert ("audit_log", "ts") not in names
    assert ("notifications_log", "fired_at") not in names


def test_target_columns_include_config_tables():
    names = {(t.name, c.name) for t, c in target_columns()}
    for expected in [
        ("channels", "created_at"), ("channels", "updated_at"),
        ("rules", "created_at"), ("rules", "updated_at"),
        ("templates", "created_at"), ("api_keys", "created_at"),
        ("schedules", "updated_at"), ("variables", "created_at"),
    ]:
        assert expected in names, expected


def test_every_current_timestamp_column_is_classified():
    """Guard against silent drift: every CURRENT_TIMESTAMP column in the
    schema must be either a repair target or an explicitly EXCLUDED log
    field — never unclassified. A newly added column fails this loudly."""
    from app.db.models import Base

    all_ct = {
        (t.name, c.name)
        for t in Base.metadata.sorted_tables
        for c in t.columns
        if _is_current_timestamp(c)
    }
    classified = {(t.name, c.name) for t, c in target_columns()} | set(EXCLUDED)
    assert all_ct == classified, all_ct ^ classified


# ── Repair conversion (local wall clock -> UTC, DST-correct) ─────────


def test_local_stored_value_converts_to_utc_summer():
    """A summer row stored as local 12:00 (EEST, UTC+3) -> 09:00 UTC."""
    cutoff = datetime(2026, 11, 12, 5, 0)
    plan = plan_corrections(
        [("row", datetime(2026, 7, 1, 12, 0))], timedelta(0), BUCHAREST, cutoff=cutoff
    )
    assert len(plan) == 1
    assert plan[0][2] == datetime(2026, 7, 1, 9, 0)   # 12:00 - 3h


def test_local_stored_value_converts_to_utc_winter():
    """A winter row stored as local 12:00 (EET, UTC+2) -> 10:00 UTC. The
    SAME single run corrects both seasons by the right amount (the R09
    flat-offset bug this avoids)."""
    cutoff = datetime(2026, 11, 12, 5, 0)
    plan = plan_corrections(
        [("row", datetime(2026, 1, 15, 12, 0))], timedelta(0), BUCHAREST, cutoff=cutoff
    )
    assert plan[0][2] == datetime(2026, 1, 15, 10, 0)  # 12:00 - 2h


def test_cutoff_skips_post_fix_rows():
    """A value at/after the cutoff was written in UTC and must not shift."""
    cutoff = datetime(2026, 11, 12, 5, 0)
    plan = plan_corrections(
        [
            ("old", datetime(2026, 7, 1, 12, 0)),        # before cutoff -> repaired
            ("new", datetime(2026, 11, 12, 6, 0)),       # after cutoff -> skipped
        ],
        timedelta(0), BUCHAREST, cutoff=cutoff,
    )
    keys = {k for k, *_ in plan}
    assert keys == {"old"}


def test_parse_cutoff_naive_and_aware():
    assert parse_cutoff("2026-11-12T05:00:00") == datetime(2026, 11, 12, 5, 0)
    # +02:00 local 07:00 -> 05:00 UTC naive
    assert parse_cutoff("2026-11-12T07:00:00+02:00") == datetime(2026, 11, 12, 5, 0)


# ── Writing created_at must NOT disturb updated_at (onupdate regression) ──


@pytest.mark.anyio
@pytest.mark.filterwarnings(
    # SQLite-only: a raw text() datetime bind hits stdlib sqlite3's deprecated
    # adapter. Irrelevant to the MySQL-targeted tool (aiomysql handles it).
    "ignore:The default datetime adapter is deprecated:DeprecationWarning"
)
async def test_correcting_created_at_leaves_updated_at_untouched(db_session):
    """A Core ``update()`` on created_at would fire the table's
    ``onupdate=CURRENT_TIMESTAMP`` and clobber updated_at. The raw per-column
    write in ``apply_column_corrections`` must not: correcting created_at
    leaves updated_at byte-for-byte as it was."""
    from app.db.models import Channel

    ch = Channel(
        name="tz_probe", kind="ui", config={},
        created_at=datetime(2026, 7, 1, 12, 0, 0),     # summer local
        updated_at=datetime(2026, 8, 15, 9, 0, 0),     # distinct, must survive
    )
    db_session.add(ch)
    await db_session.flush()
    rid = ch.id
    original_updated = ch.updated_at

    table = Channel.__table__
    pk_cols = list(table.primary_key.columns)
    plan = plan_corrections(
        [((rid,), ch.created_at)], timedelta(0), BUCHAREST,
        cutoff=datetime(2027, 1, 1),
    )
    assert len(plan) == 1
    await apply_column_corrections(db_session, table, pk_cols, table.c.created_at, plan)

    db_session.expire(ch)
    refreshed = await db_session.get(Channel, rid)
    assert refreshed.created_at == datetime(2026, 7, 1, 9, 0, 0)   # -3h, corrected
    assert refreshed.updated_at == original_updated                # untouched
