"""Tests for app.core.schedule_service.

Cron-driven dispatcher. We test pure cron computation in isolation
and drive _tick() with mocked dispatcher to assert the firing path.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core.schedule_service import ScheduleService, get_schedule_service
from app.db.models import (
    ChannelKind,
    Delivery,
    DeliveryState,
    NotificationLog,
    Schedule,
    ScheduleOccurrence,
    Severity,
    TemplateChannel,
)


def _ok_dispatch(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    async def inner():
        return DispatchOutcome(succeeded=list(channel_names), failed={})
    return inner()


@pytest.fixture
def svc():
    s = ScheduleService(tick_sec=0.01)
    s._tz = ZoneInfo("UTC")
    return s


# ── Cron computation ─────────────────────────────────────────────


def test_next_cron_simple_expression(svc):
    """`*/5 * * * *` from 12:00:00 → 12:05:00."""
    anchor = datetime(2026, 5, 10, 12, 0, 0)
    nxt = svc._next_cron("*/5 * * * *", anchor)
    assert nxt == datetime(2026, 5, 10, 12, 5, 0)


def test_next_cron_daily_2100(svc):
    """`0 21 * * *` from 12:00 → same-day 21:00."""
    anchor = datetime(2026, 5, 10, 12, 0, 0)
    nxt = svc._next_cron("0 21 * * *", anchor)
    assert nxt == datetime(2026, 5, 10, 21, 0, 0)


def test_next_cron_rolls_over_to_next_day(svc):
    """Anchor after 21:00 → next 21:00 is tomorrow."""
    anchor = datetime(2026, 5, 10, 22, 0, 0)
    nxt = svc._next_cron("0 21 * * *", anchor)
    assert nxt == datetime(2026, 5, 11, 21, 0, 0)


def test_next_cron_with_timezone(svc):
    """When tz=Europe/Bucharest (UTC+3 summer), 21:00 local → 18:00 UTC."""
    svc._tz = ZoneInfo("Europe/Bucharest")
    anchor_utc = datetime(2026, 7, 10, 12, 0, 0)  # July → DST = UTC+3
    nxt_utc = svc._next_cron("0 21 * * *", anchor_utc)
    # 21:00 Bucharest in July = 18:00 UTC
    assert nxt_utc.hour == 18


def test_next_cron_invalid_raises(svc):
    with pytest.raises(Exception):
        svc._next_cron("not a cron", datetime(2026, 5, 10))


# ── _init_next_fire_times ────────────────────────────────────────


async def test_init_assigns_next_fire_times(db_engine, db_session, svc):
    db_session.add(Schedule(
        id=1, name="daily", cron_expr="0 21 * * *",
        template_type="daily_summary", context={}, enabled=True,
    ))
    await db_session.commit()

    await svc._init_next_fire_times()

    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 1))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.next_fire_at is not None


async def test_init_disables_invalid_cron(db_engine, db_session, svc):
    db_session.add(Schedule(
        id=2, name="bad", cron_expr="garbage",
        template_type="x", context={}, enabled=True,
    ))
    await db_session.commit()

    await svc._init_next_fire_times()

    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 2))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.enabled is False


async def test_init_skips_already_set(db_engine, db_session, svc):
    """Schedules with next_fire_at already populated must not be
    overwritten on init."""
    pre_set = datetime(2030, 1, 1, 12, 0, 0)
    db_session.add(Schedule(
        id=3, name="preset", cron_expr="0 21 * * *",
        template_type="x", context={}, enabled=True,
        next_fire_at=pre_set,
    ))
    await db_session.commit()

    await svc._init_next_fire_times()

    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 3))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.next_fire_at == pre_set


# ── _tick fires due schedules ────────────────────────────────────


async def test_tick_fires_due_schedule(db_engine, db_session, svc, make_template):
    t = make_template(type="daily_t", min_repeat_min=0)
    db_session.add(t)
    db_session.add(Schedule(
        id=10, name="due", cron_expr="0 21 * * *",
        template_type="daily_t", context={"k": "v"},
        enabled=True,
        next_fire_at=datetime.utcnow() - timedelta(seconds=10),  # due
    ))
    await db_session.commit()

    fake_fire = AsyncMock(
        return_value=type("R", (), {"id": "x", "dispatched": True})()
    )
    with patch("app.core.schedule_service.dispatcher_module.fire", fake_fire):
        await svc._tick()
    fake_fire.assert_called_once()
    # Envelope inspection
    env = fake_fire.call_args.args[0]
    assert env.type == "daily_t"
    assert env.context == {"k": "v"}
    assert env.source == "schedule:due"


async def test_tick_skips_overdue_beyond_grace(db_engine, db_session, svc):
    """Schedules overdue beyond _RESUME_GRACE_SEC are not fired —
    they're advanced and skipped."""
    db_session.add(Schedule(
        id=11, name="stale", cron_expr="0 21 * * *",
        template_type="x", context={}, enabled=True,
        next_fire_at=datetime.utcnow() - timedelta(hours=2),
    ))
    await db_session.commit()

    fake_fire = AsyncMock()
    with patch("app.core.schedule_service.dispatcher_module.fire", fake_fire):
        await svc._tick()
    fake_fire.assert_not_called()
    # next_fire_at should have been advanced
    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 11))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.next_fire_at > datetime.utcnow()


async def test_schedule_crash_after_advance_loses_intent(db_engine, db_session, svc):
    """V05: advancing next_fire_at and persisting the notification intent must
    be ATOMIC. If the fire crashes before the intent is durable, next_fire_at
    must stay put so the occurrence is retried, not silently lost. (Replaces
    the old advance-first R02 test, whose advance-then-fire ordering turned a
    duplicate risk into this loss.)"""
    original = datetime.utcnow() - timedelta(seconds=10)
    db_session.add(Schedule(
        id=50, name="v05", cron_expr="*/5 * * * *",
        template_type="x", context={}, enabled=True, next_fire_at=original,
    ))
    await db_session.commit()
    # Read the STORED value back (MySQL DATETIME rounds to whole seconds, so an
    # exact compare against the in-memory microsecond value is wrong) — an
    # unchanged next_fire_at means the occurrence is still due, not lost.
    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 50))
    ).scalar_one()
    await db_session.refresh(sched)
    stored_before = sched.next_fire_at

    # The dispatcher crashes before it can persist/commit the durable intent.
    with patch(
        "app.core.schedule_service.dispatcher_module.fire",
        new=AsyncMock(side_effect=RuntimeError("crash mid-fire")),
    ):
        await svc._tick()

    await db_session.refresh(sched)
    # next_fire_at unchanged → still due, will be retried (no lost occurrence).
    assert sched.next_fire_at == stored_before
    # No occurrence guard was left behind for an intent that never persisted.
    occ = (await db_session.execute(
        select(ScheduleOccurrence).where(ScheduleOccurrence.schedule_id == 50)
    )).scalars().all()
    assert occ == []


async def test_schedule_savepoint_incompatible_with_dispatch_commit(
    db_engine, db_session, svc, make_template, make_channel
):
    """V06: firing a schedule through the REAL dispatcher must complete. The
    old code wrapped fire() in begin_nested while the dispatcher commits its
    own durable intent, so the savepoint context raised and the fire was
    swallowed — last_fired_at stayed null and the delivery was stuck at
    attempts=0. With the savepoint gone, the fire settles normally."""
    t = make_template(type="sched_real", min_repeat_min=0)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c.id, severity_min=Severity.info, enabled=True,
    ))
    pre = datetime.utcnow() - timedelta(seconds=5)
    db_session.add(Schedule(
        id=60, name="v06", cron_expr="*/5 * * * *",
        template_type="sched_real", context={}, enabled=True, next_fire_at=pre,
    ))
    await db_session.commit()

    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok_dispatch):
        await svc._tick()

    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 60))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.last_fired_at is not None  # the fire actually completed
    # The delivery ran its first attempt and settled sent — not stuck at 0.
    log = (await db_session.execute(
        select(NotificationLog).where(NotificationLog.type == "sched_real")
    )).scalar_one()
    d = (await db_session.execute(
        select(Delivery).where(Delivery.notification_id == log.id)
    )).scalar_one()
    assert d.attempts >= 1
    assert d.state == DeliveryState.sent
    # The occurrence guard is linked to the fire it produced.
    occ = (await db_session.execute(
        select(ScheduleOccurrence).where(ScheduleOccurrence.schedule_id == 60)
    )).scalar_one()
    assert occ.notification_id == log.id


async def test_schedule_occurrence_guard_blocks_duplicate_fire(
    db_engine, db_session, svc, make_template
):
    """V05: a second tick that somehow re-selects the same occurrence (its
    next_fire_at reset to an already-fired time) must not fire again — the
    (schedule_id, scheduled_at) guard rejects it."""
    t = make_template(type="occ_t", min_repeat_min=0)
    db_session.add(t)
    pre = datetime.utcnow() - timedelta(seconds=5)
    db_session.add(Schedule(
        id=70, name="occ", cron_expr="*/5 * * * *",
        template_type="occ_t", context={}, enabled=True, next_fire_at=pre,
    ))
    # A guard already exists for this exact occurrence (previous fire).
    db_session.add(ScheduleOccurrence(schedule_id=70, scheduled_at=pre))
    await db_session.commit()

    fake_fire = AsyncMock(return_value=type("R", (), {"id": "x", "dispatched": True})())
    with patch("app.core.schedule_service.dispatcher_module.fire", fake_fire):
        await svc._tick()
    fake_fire.assert_not_called()  # the guard blocked the duplicate fire


async def test_tick_skips_disabled(db_engine, db_session, svc):
    db_session.add(Schedule(
        id=12, name="off", cron_expr="*/5 * * * *",
        template_type="x", context={}, enabled=False,
        next_fire_at=datetime.utcnow() - timedelta(seconds=10),
    ))
    await db_session.commit()

    fake_fire = AsyncMock()
    with patch("app.core.schedule_service.dispatcher_module.fire", fake_fire):
        await svc._tick()
    fake_fire.assert_not_called()


async def test_tick_advances_next_fire_after_fire(db_engine, db_session, svc, make_template):
    t = make_template(type="adv_t", min_repeat_min=0)
    db_session.add(t)
    pre = datetime.utcnow() - timedelta(seconds=5)
    db_session.add(Schedule(
        id=13, name="adv", cron_expr="*/5 * * * *",
        template_type="adv_t", context={}, enabled=True,
        next_fire_at=pre,
    ))
    await db_session.commit()

    fake_fire = AsyncMock(
        return_value=type("R", (), {"id": "x", "dispatched": True})()
    )
    with patch("app.core.schedule_service.dispatcher_module.fire", fake_fire):
        await svc._tick()

    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 13))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.next_fire_at > pre
    assert sched.last_fired_at is not None


# ── recompute_next_fire (CRUD hook) ──────────────────────────────


async def test_recompute_next_fire_computes_for_enabled(db_engine, db_session, svc):
    db_session.add(Schedule(
        id=14, name="rc", cron_expr="0 12 * * *",
        template_type="x", context={}, enabled=True,
    ))
    await db_session.commit()

    await svc.recompute_next_fire(14)

    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 14))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.next_fire_at is not None


async def test_recompute_disabled_clears_next_fire(db_engine, db_session, svc):
    db_session.add(Schedule(
        id=15, name="rc_off", cron_expr="0 12 * * *",
        template_type="x", context={}, enabled=False,
        next_fire_at=datetime(2030, 1, 1),
    ))
    await db_session.commit()

    await svc.recompute_next_fire(15)

    sched = (
        await db_session.execute(select(Schedule).where(Schedule.id == 15))
    ).scalar_one()
    await db_session.refresh(sched)
    assert sched.next_fire_at is None


async def test_recompute_unknown_id_no_op(db_engine, svc):
    # Doesn't raise, doesn't error
    await svc.recompute_next_fire(99999)


# ── Lifecycle ────────────────────────────────────────────────────


async def test_start_idempotent(db_engine):
    svc = ScheduleService(tick_sec=0.01)
    await svc.start()
    task = svc._task
    await svc.start()
    assert svc._task is task
    await svc.stop()


async def test_stop_clears_task(db_engine):
    svc = ScheduleService(tick_sec=0.01)
    await svc.start()
    assert svc._task is not None
    await svc.stop()
    assert svc._task is None


async def test_start_falls_back_to_utc_on_bad_tz(db_engine, monkeypatch):
    """Invalid TZ in settings should not crash startup."""
    from app import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "tz", "Not/A/Zone")
    svc = ScheduleService(tick_sec=0.01)
    await svc.start()
    assert svc._tz == ZoneInfo("UTC")
    await svc.stop()


def test_get_schedule_service_singleton():
    a = get_schedule_service()
    b = get_schedule_service()
    assert a is b
