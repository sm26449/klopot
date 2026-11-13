"""Regression tests for audit A05 — channel-scope snooze and the
channel's own quiet_hours were accepted/stored but never applied by the
gating runtime (it read only Template.quiet_hours and type/rule snoozes).

Reproduced from ``extra-results.json → channel_snooze, channel_quiet_fire``.
"""
from __future__ import annotations

from datetime import time, timedelta
from unittest.mock import patch

import pytest

from app.core.gating import (
    GateInput,
    _channel_window,
    _strip_quiet_channels,
    evaluate,
)
from app.db.models import ChannelKind, Snooze, SnoozeScope
from app.utils.time import utc_now

pytestmark = pytest.mark.anyio

_TZ_NOW = "app.core.gating._tz_now_time"


@pytest.fixture
async def template(db_session, make_template):
    t = make_template(min_repeat_min=0)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


async def _add_snooze(db_session, scope, target, *, minutes=30):
    db_session.add(Snooze(scope=scope, target=target, until=utc_now() + timedelta(minutes=minutes)))
    await db_session.commit()


# ── channel-scope snooze ──────────────────────────────────────────


async def test_channel_snooze_strips_only_that_channel(template, db_session):
    await _add_snooze(db_session, SnoozeScope.channel, "telegram")
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui", "telegram"]),
        db_session,
    )
    assert d.allowed is True
    assert d.channels == ["ui"]


async def test_channel_snooze_all_channels_denies(template, db_session):
    await _add_snooze(db_session, SnoozeScope.channel, "ui")
    await _add_snooze(db_session, SnoozeScope.channel, "telegram")
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui", "telegram"]),
        db_session,
    )
    assert d.allowed is False
    assert d.reason == "snoozed"


async def test_expired_channel_snooze_does_not_strip(template, db_session):
    await _add_snooze(db_session, SnoozeScope.channel, "telegram", minutes=-5)
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui", "telegram"]),
        db_session,
    )
    assert d.channels == ["ui", "telegram"]


async def test_test_fire_respects_channel_snooze(template, db_session):
    """Snooze is a gate-2 mute, respected even by test fires."""
    await _add_snooze(db_session, SnoozeScope.channel, "ui")
    d = await evaluate(
        GateInput(template=template, rule_id=None, channel_names=["ui"], test=True),
        db_session,
    )
    assert d.reason == "snoozed"


# ── channel's own quiet_hours ─────────────────────────────────────


async def test_channel_own_quiet_hours_strips(template, db_session, make_channel):
    c = make_channel(name="ui", kind=ChannelKind.ui, quiet_hours={"window": "22-07"})
    db_session.add(c)
    await db_session.commit()
    with patch(_TZ_NOW, return_value=time(3, 0)):  # 03:00 ∈ 22-07
        d = await evaluate(
            GateInput(template=template, rule_id=None, channel_names=["ui"]),
            db_session,
        )
    assert d.allowed is False
    assert d.reason == "gated"


async def test_channel_quiet_hours_outside_window_passes(template, db_session, make_channel):
    c = make_channel(name="ui", kind=ChannelKind.ui, quiet_hours={"window": "22-07"})
    db_session.add(c)
    await db_session.commit()
    with patch(_TZ_NOW, return_value=time(12, 0)):  # noon ∉ 22-07
        d = await evaluate(
            GateInput(template=template, rule_id=None, channel_names=["ui"]),
            db_session,
        )
    assert d.channels == ["ui"]


async def test_test_fire_bypasses_channel_quiet(template, db_session, make_channel):
    """Quiet hours is a silencing gate (4) — test fires skip it."""
    c = make_channel(name="ui", kind=ChannelKind.ui, quiet_hours={"window": "22-07"})
    db_session.add(c)
    await db_session.commit()
    with patch(_TZ_NOW, return_value=time(3, 0)):
        d = await evaluate(
            GateInput(template=template, rule_id=None, channel_names=["ui"], test=True),
            db_session,
        )
    assert d.channels == ["ui"]


# ── pure helpers ──────────────────────────────────────────────────


def test_strip_applies_channel_window():
    out = _strip_quiet_channels(
        ["ui", "tg"], {}, {"ui": {"window": "22-07"}}, now_t=time(3, 0)
    )
    assert out == ["tg"]


def test_strip_template_and_channel_windows_union():
    out = _strip_quiet_channels(
        ["ui", "tg", "sms"],
        {"tg": "22-07"},                    # template mutes tg
        {"ui": {"window": "22-07"}},        # channel mutes ui
        now_t=time(3, 0),
    )
    assert out == ["sms"]


def test_channel_window_extraction():
    assert _channel_window({"window": "22-07"}) == "22-07"
    assert _channel_window("22-07") == "22-07"
    assert _channel_window({}) is None
    assert _channel_window(None) is None
    assert _channel_window({"nope": 1}) is None
