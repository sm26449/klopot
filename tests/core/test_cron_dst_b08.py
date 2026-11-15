"""B-08: a daily cron must keep its civil firing time across a DST
transition.

The old implementation fed croniter a timezone-aware anchor, so croniter
3.x carried the anchor's fixed UTC offset across the boundary and the
firing hour drifted — a ``03:30`` daily alert in ``Europe/Bucharest``
fired at ``04:30`` the day *after* the autumn fall-back. The fix drives
croniter on naive local wall time and localizes afterwards, via the
shared :mod:`app.utils.cron` helper that also backs the editor preview.

These tests pin the corrected civil times across both Bucharest DST
boundaries, prove the fired and previewed instants agree, and keep a
negative control that the old aware-anchor path drifts.
"""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from croniter import croniter

from app.core.schedule_service import ScheduleService
from app.utils.cron import cron_next_utc, cron_preview_local

BUCHAREST = ZoneInfo("Europe/Bucharest")


def _local_hhmm(naive_utc: datetime) -> str:
    """Render a naive-UTC instant as Bucharest wall-clock HH:MM."""
    return naive_utc.replace(tzinfo=UTC).astimezone(BUCHAREST).strftime("%H:%M")


def _chain(cron: str, start_utc: datetime, tz: ZoneInfo, n: int) -> list[datetime]:
    """Follow the real service loop: each next_fire_at is the anchor for
    the following computation. Returns naive-UTC instants."""
    out: list[datetime] = []
    anchor = start_utc
    for _ in range(n):
        anchor = cron_next_utc(cron, anchor, tz)
        out.append(anchor)
    return out


# ── The exact B-08 scenario ──────────────────────────────────────────


def test_daily_keeps_civil_time_across_autumn_fallback():
    """Daily 03:30 Bucharest. The autumn fall-back is 2026-10-25 (04:00
    EEST → 03:00 EET). Every occurrence, including the day AFTER, must
    stay at 03:30 local — never 04:30."""
    # Start the evening before the transition.
    chain = _chain("30 3 * * *", datetime(2026, 10, 24, 0, 0), BUCHAREST, 4)
    assert [_local_hhmm(dt) for dt in chain] == ["03:30", "03:30", "03:30", "03:30"]
    # The day-after instant is 01:30 UTC (03:30 EET), not 02:30 UTC (04:30).
    day_after = next(dt for dt in chain if dt.date() == datetime(2026, 10, 26).date())
    assert day_after == datetime(2026, 10, 26, 1, 30)


def test_negative_control_old_aware_anchor_path_drifts():
    """Proof the regression is real: the OLD approach — a tz-aware anchor
    handed straight to croniter — drifts to 04:30 the day after the
    fall-back. If croniter is ever patched so this no longer drifts, this
    control fails loudly and we can simplify."""
    anchor_utc = datetime(2026, 10, 25, 0, 30)  # just after the 10-25 fire
    aware = anchor_utc.replace(tzinfo=UTC).astimezone(BUCHAREST)
    nxt = croniter("30 3 * * *", aware).get_next(datetime)
    nxt_utc = nxt.astimezone(UTC).replace(tzinfo=None)
    assert _local_hhmm(nxt_utc) == "04:30"  # the bug
    # The corrected helper from the same anchor does NOT drift.
    assert _local_hhmm(cron_next_utc("30 3 * * *", anchor_utc, BUCHAREST)) == "03:30"


def test_daily_keeps_civil_time_across_spring_forward():
    """Daily 03:30 Bucharest. Spring-forward is 2026-03-29 (03:00 EET →
    04:00 EEST), so 03:30 is skipped that one day; per the gap policy it
    resolves to the pre-transition offset (04:30 local) and the following
    day returns to 03:30."""
    chain = _chain("30 3 * * *", datetime(2026, 3, 28, 0, 0), BUCHAREST, 4)
    labels = [_local_hhmm(dt) for dt in chain]
    assert labels[0] == "03:30"           # 2026-03-28, before the jump
    assert labels[1] == "04:30"           # 2026-03-29, gap day
    assert labels[2] == "03:30"           # 2026-03-30, back to normal
    assert labels[3] == "03:30"


def test_fallback_first_occurrence_uses_earlier_offset():
    """The ambiguous fall-back time resolves to the FIRST (pre-transition,
    UTC+3) occurrence: 03:30 EEST = 00:30 UTC on 2026-10-25."""
    nxt = cron_next_utc("30 3 * * *", datetime(2026, 10, 24, 12, 0), BUCHAREST)
    assert nxt == datetime(2026, 10, 25, 0, 30)


# ── Preview / runtime parity (what the audit demands) ────────────────


def test_preview_and_runtime_agree_across_fallback():
    """The editor preview and the firing runtime must compute identical
    instants, so a user never previews a time the service won't honour."""
    start = datetime(2026, 10, 24, 0, 0)
    preview = cron_preview_local("30 3 * * *", start, BUCHAREST, 4)
    runtime = _chain("30 3 * * *", start, BUCHAREST, 4)
    preview_utc = [dt.astimezone(UTC).replace(tzinfo=None) for dt in preview]
    assert preview_utc == runtime
    # And the preview's local wall times are all 03:30.
    assert [dt.strftime("%H:%M") for dt in preview] == ["03:30"] * 4


def test_preview_returns_aware_local_datetimes():
    preview = cron_preview_local("0 21 * * *", datetime(2026, 7, 1, 0, 0), BUCHAREST, 3)
    assert all(dt.tzinfo is not None for dt in preview)
    assert all(dt.hour == 21 for dt in preview)        # 21:00 local
    assert all(dt.utcoffset().total_seconds() == 3 * 3600 for dt in preview)  # UTC+3 summer


# ── Service wrapper delegates to the shared helper ───────────────────


def test_service_next_cron_matches_helper_across_boundary():
    svc = ScheduleService(tick_sec=0.01)
    svc._tz = BUCHAREST
    anchor = datetime(2026, 10, 25, 0, 30)
    assert svc._next_cron("30 3 * * *", anchor) == cron_next_utc(
        "30 3 * * *", anchor, BUCHAREST
    )


def test_utc_timezone_has_no_dst_drift():
    """A UTC-configured service keeps exact wall times with no transition."""
    chain = _chain("30 3 * * *", datetime(2026, 10, 24, 0, 0), ZoneInfo("UTC"), 3)
    assert chain == [
        datetime(2026, 10, 24, 3, 30),
        datetime(2026, 10, 25, 3, 30),
        datetime(2026, 10, 26, 3, 30),
    ]
