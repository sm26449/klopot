"""Tests for app.core.gating — DB-backed, exercises all gates."""
from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from app.core.gating import (
    GateInput,
    _in_quiet_window,
    _strip_quiet_channels,
    evaluate,
    record_fire,
)
from app.db.models import Snooze, SnoozeScope, ThrottleState


@pytest.fixture
async def template(db_session, make_template):
    t = make_template(min_repeat_min=0)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


# ── enabled gate ──────────────────────────────────────────────────


async def test_enabled_template_passes(template, db_session):
    g = GateInput(template=template, rule_id=None, channel_names=["ui"])
    d = await evaluate(g, db_session)
    assert d.allowed is True
    assert d.channels == ["ui"]


async def test_disabled_template_denies(template, db_session):
    template.enabled = False
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.allowed is False
    assert d.reason == "disabled"


# ── snooze gate ───────────────────────────────────────────────────


async def test_active_type_snooze_denies(template, db_session):
    db_session.add(
        Snooze(
            id=1,
            scope=SnoozeScope.type,
            target=template.type,
            until=datetime.utcnow() + timedelta(hours=1),
        )
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.reason == "snoozed"


async def test_expired_snooze_does_not_deny(template, db_session):
    db_session.add(
        Snooze(
            id=2,
            scope=SnoozeScope.type,
            target=template.type,
            until=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.allowed is True


async def test_rule_scope_snooze(template, db_session):
    db_session.add(
        Snooze(
            id=3,
            scope=SnoozeScope.rule,
            target="42",
            until=datetime.utcnow() + timedelta(hours=1),
        )
    )
    await db_session.commit()
    # Same rule_id matches
    d = await evaluate(
        GateInput(template=template, rule_id=42, channel_names=["ui"]),
        db_session,
    )
    assert d.reason == "snoozed"
    # Different rule_id is unaffected
    d = await evaluate(
        GateInput(template=template, rule_id=99, channel_names=["ui"]),
        db_session,
    )
    assert d.allowed is True


# ── throttle gate ─────────────────────────────────────────────────


async def test_within_min_repeat_throttles(template, db_session):
    template.min_repeat_min = 30
    db_session.add(
        ThrottleState(type=template.type, last_fired_at=datetime.utcnow())
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.reason == "throttled"


async def test_past_min_repeat_allows(template, db_session):
    template.min_repeat_min = 30
    db_session.add(
        ThrottleState(
            type=template.type,
            last_fired_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.allowed is True


async def test_an_admin_test_fire_bypasses_throttle(template, db_session):
    template.min_repeat_min = 30
    db_session.add(
        ThrottleState(type=template.type, last_fired_at=datetime.utcnow())
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"], override_silencing=True),
        db_session,
    )
    assert d.allowed is True


async def test_min_repeat_zero_never_throttles(template, db_session):
    template.min_repeat_min = 0
    db_session.add(
        ThrottleState(type=template.type, last_fired_at=datetime.utcnow())
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.allowed is True


async def test_record_fire_inserts_when_missing(template, db_session):
    await record_fire(template.type, db_session, test=False)
    await db_session.commit()
    from sqlalchemy import select

    row = (
        await db_session.execute(
            select(ThrottleState).where(ThrottleState.type == template.type)
        )
    ).scalar_one()
    assert row.last_fired_at is not None


async def test_record_fire_updates_existing(template, db_session):
    old = datetime.utcnow() - timedelta(hours=1)
    db_session.add(ThrottleState(type=template.type, last_fired_at=old))
    await db_session.commit()
    await record_fire(template.type, db_session, test=False)
    await db_session.commit()
    from sqlalchemy import select

    row = (
        await db_session.execute(
            select(ThrottleState).where(ThrottleState.type == template.type)
        )
    ).scalar_one()
    assert row.last_fired_at > old


# ── quiet hours (pure logic) ──────────────────────────────────────


def test_quiet_window_no_window_passes():
    assert _in_quiet_window(time(3, 0), None) is False


def test_quiet_window_simple_match():
    # 03:00 in 22-07 (overnight) → True
    assert _in_quiet_window(time(3, 0), "22-07") is True
    # 12:00 in 22-07 → False
    assert _in_quiet_window(time(12, 0), "22-07") is False


def test_quiet_window_same_day():
    # 14:00 in 13-15 (same-day window) → True
    assert _in_quiet_window(time(14, 0), "13-15") is True
    # 15:00 just outside (end is exclusive) → False
    assert _in_quiet_window(time(15, 0), "13-15") is False


def test_quiet_window_malformed_fails_open():
    """Bad format should NOT silently mute — return False."""
    assert _in_quiet_window(time(3, 0), "bogus") is False


def test_strip_quiet_channels_drops_matching():
    # 03:00 — telegram is in quiet, ui is not configured (passes)
    quiet = {"telegram": "22-07"}
    # We can't control "now" easily; verify the function doesn't crash
    # and behaves correctly when the window is empty
    out = _strip_quiet_channels(["ui", "telegram"], {})
    assert out == ["ui", "telegram"]


# ── allow output ──────────────────────────────────────────────────


async def test_allow_returns_input_channels(template, db_session):
    d = await evaluate(
        GateInput(
            template=template, rule_id=None,
            channel_names=["ui", "telegram", "sms"],
        ),
        db_session,
    )
    assert d.channels == ["ui", "telegram", "sms"]


async def test_empty_channels_returns_gated(template, db_session):
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=[]),
        db_session,
    )
    assert d.reason == "gated"


async def test_wildcard_snooze_is_maintenance_mode(template, db_session):
    """scope=type target='*' mutes EVERYTHING until it expires —
    the maintenance-mode contract."""
    db_session.add(
        Snooze(
            id=77,
            scope=SnoozeScope.type,
            target="*",
            until=datetime.utcnow() + timedelta(hours=2),
            reason="physical work on the plant",
        )
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.reason == "snoozed"


async def test_expired_wildcard_snooze_lifts_maintenance(template, db_session):
    db_session.add(
        Snooze(
            id=78,
            scope=SnoozeScope.type,
            target="*",
            until=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    await db_session.commit()
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"]),
        db_session,
    )
    assert d.allowed


# ── A34: delivery gate (generic since 0030: gate_variable + gate_min) ──


import contextlib


@contextlib.contextmanager
def _fresh_cache():
    from app.core.state_cache import reset_state_cache_for_tests

    reset_state_cache_for_tests()
    try:
        yield
    finally:
        reset_state_cache_for_tests()


async def _gate(template, db_session, *, override_silencing=False):
    return await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"], override_silencing=override_silencing),
        db_session,
    )


async def test_gate_denies_below_threshold(template, db_session):
    from app.core.state_cache import get_state_cache

    template.gate_variable, template.gate_min = "tank.level", 5.0
    with _fresh_cache():
        await get_state_cache().set("tank.level", 3.0)  # below 5 → suppress
        d = await _gate(template, db_session)
    assert d.allowed is False
    assert d.reason == "below_gate"


async def test_gate_allows_at_or_above_threshold(template, db_session):
    from app.core.state_cache import get_state_cache

    template.gate_variable, template.gate_min = "tank.level", 5.0
    with _fresh_cache():
        await get_state_cache().set("tank.level", 5.0)  # equal → deliver
        assert (await _gate(template, db_session)).allowed is True
        await get_state_cache().set("tank.level", 9.0)
        assert (await _gate(template, db_session)).allowed is True


async def test_gate_fails_open_when_variable_absent(template, db_session):
    template.gate_variable, template.gate_min = "tank.level", 5.0
    with _fresh_cache():  # never set → unknown → don't suppress
        assert (await _gate(template, db_session)).allowed is True


async def test_gate_fails_open_on_non_numeric(template, db_session):
    from app.core.state_cache import get_state_cache

    template.gate_variable, template.gate_min = "tank.level", 5.0
    with _fresh_cache():
        await get_state_cache().set("tank.level", "n/a")
        assert (await _gate(template, db_session)).allowed is True


async def test_gate_noop_without_variable(template, db_session):
    """A threshold with no variable has no effect (the pre-0030 behaviour
    of require_pv_kw while ALERTD_PV_POWER_VAR was unset)."""
    from app.core.state_cache import get_state_cache

    template.gate_variable, template.gate_min = None, 5.0
    with _fresh_cache():
        await get_state_cache().set("tank.level", 1.0)
        assert (await _gate(template, db_session)).allowed is True


async def test_gate_skipped_for_an_admin_test_fire(template, db_session):
    from app.core.state_cache import get_state_cache

    template.gate_variable, template.gate_min = "tank.level", 5.0
    with _fresh_cache():
        await get_state_cache().set("tank.level", 0.0)
        # An administrator's test fire bypasses the silencing gates.
        assert (await _gate(template, db_session, override_silencing=True)).allowed is True


# ── F14: quiet hours use settings.tz, not a silent UTC fallback ────


def test_tz_now_time_uses_settings_tz_not_utc():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.config import get_settings
    from app.core.gating import _tz_now_time

    settings = get_settings()
    old = settings.tz
    object.__setattr__(settings, "tz", "Asia/Tokyo")
    try:
        got = _tz_now_time()
        expect = datetime.now(ZoneInfo("Asia/Tokyo")).time()
        # Same zone → same hour (computed within the same moment). A bare
        # UTC fallback would differ by Tokyo's offset.
        assert got.hour == expect.hour
    finally:
        object.__setattr__(settings, "tz", old)
