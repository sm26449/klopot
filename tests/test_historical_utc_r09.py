"""R09: per-row DST-correct re-normalisation of the flat-offset UTC migrations.

Migrations 0004/0005 subtracted a single offset from every naive-local row, so
rows from a different DST season than the migration ran are off by the DST
delta. These tests pin the correction maths on the pure helpers in
``app.utils.historical_utc`` — no DB needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.utils.historical_utc import correct_utc, plan_corrections, zone_offset_at

BUCHAREST = ZoneInfo("Europe/Bucharest")
PLUS3 = timedelta(hours=3)  # EEST — what the migrations (run in summer) applied


def test_zone_offset_is_dst_aware():
    # Winter is EET (+02:00); summer is EEST (+03:00).
    assert zone_offset_at(BUCHAREST, datetime(2026, 1, 15, 8, 30)) == timedelta(hours=2)
    assert zone_offset_at(BUCHAREST, datetime(2026, 7, 15, 8, 30)) == timedelta(hours=3)


def test_summer_row_is_unchanged():
    # Written in summer (EEST +03:00); migration applied +03:00 → already correct.
    # local 2026-07-15 08:30 → true UTC 05:30; stored = 05:30.
    stored = datetime(2026, 7, 15, 5, 30)
    assert correct_utc(stored, PLUS3, BUCHAREST) == stored


def test_winter_row_is_corrected_by_one_hour():
    # Written in winter (EET +02:00) but the summer migration subtracted +03:00,
    # so the stored UTC is one hour too early. Correct it back.
    original_local = datetime(2026, 1, 15, 8, 30)  # EET, true UTC 06:30
    stored = original_local - PLUS3                # 05:30 — WRONG (off by -1h)
    corrected = correct_utc(stored, PLUS3, BUCHAREST)
    assert corrected == datetime(2026, 1, 15, 6, 30)
    assert corrected - stored == timedelta(hours=1)


def test_round_trip_recovers_true_utc_for_both_seasons():
    # For any original local instant, applying the flat offset then correcting
    # yields the DST-correct UTC regardless of the row's season.
    for local in (datetime(2026, 1, 20, 9, 0), datetime(2026, 8, 20, 9, 0)):
        true_utc = local.replace(tzinfo=BUCHAREST).utctimetuple()
        true_utc_dt = datetime(*true_utc[:6])
        stored = local - PLUS3  # what the flat-offset migration left
        assert correct_utc(stored, PLUS3, BUCHAREST) == true_utc_dt


def test_plan_corrections_filters_unchanged_and_null():
    rows = [
        (1, datetime(2026, 7, 15, 5, 30)),   # summer, correct → skipped
        (2, datetime(2026, 1, 15, 8, 30) - PLUS3),  # winter, wrong → included
        (3, None),                            # null → skipped
    ]
    plan = plan_corrections(rows, PLUS3, BUCHAREST)
    assert [p[0] for p in plan] == [2]
    _id, old, new, delta = plan[0]
    assert new == datetime(2026, 1, 15, 6, 30)
    assert delta == timedelta(hours=1)


def test_cutoff_excludes_post_migration_rows():
    # The table is a mix: pre-migration rows were flat-offset converted, but
    # rows written AFTER the migration are already correct native UTC. A
    # post-migration winter row looks "correctable" (its UTC + applied offset
    # lands in a +02:00 window) but must be left alone — the cutoff enforces it.
    migration_run = datetime(2026, 7, 6, 20, 30)  # 0005
    post_winter = datetime(2026, 11, 20, 2, 0)    # written native-UTC, after migration
    pre_winter = datetime(2026, 2, 10, 8, 30) - PLUS3  # genuine pre-migration target
    rows = [(1, post_winter), (2, pre_winter)]
    # Without a cutoff the correct post-migration row is wrongly flagged…
    assert {p[0] for p in plan_corrections(rows, PLUS3, BUCHAREST)} == {1, 2}
    # …with the cutoff only the genuine pre-migration row survives.
    bounded = plan_corrections(rows, PLUS3, BUCHAREST, cutoff=migration_run)
    assert [p[0] for p in bounded] == [2]


def test_correction_is_a_fixed_point_on_already_correct_data():
    # Applying the correction to a table where every row's season matches the
    # applied offset changes nothing (an accidental dry-run-then-apply on a
    # correct DB is a no-op for those rows).
    summer_rows = [(i, datetime(2026, 7, 1 + i, 5, 30)) for i in range(5)]
    assert plan_corrections(summer_rows, PLUS3, BUCHAREST) == []


def test_utc_host_migration_left_rows_as_local_and_offset_zero_normalises_them():
    # If the migration ran on a UTC host (offset 0), it subtracted nothing and
    # left rows as naive LOCAL. Running the tool with --applied-offset 00:00
    # recovers the local wall time (== stored) and normalises to true UTC.
    local = datetime(2026, 1, 15, 8, 30)  # EET, true UTC 06:30
    stored_local = local                   # migration did nothing
    assert correct_utc(stored_local, timedelta(0), BUCHAREST) == datetime(2026, 1, 15, 6, 30)
