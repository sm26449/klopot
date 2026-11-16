"""An episode nobody was told about is announced by a later firing (audit P05).

The episode is opened before the gates decide whether its notice goes out. If
that first firing was snoozed, in quiet hours, throttled or failed on every
channel, later firings were plain repeats — which notify nothing — and the
alert stayed silent for as long as it lasted.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select, update

from app.core import fire_service
from app.db.models import (
    Channel,
    ChannelKind,
    Incident,
    NotificationLog,
    Severity,
    Snooze,
    SnoozeScope,
    Template,
    TemplateChannel,
    ThrottleState,
)
from app.utils.time import utc_now
from tests._db import fresh


async def _setup(db_session, *, min_repeat_min=0):
    ch = Channel(name="ui_episodes", kind=ChannelKind.ui, config={}, enabled=True)
    tpl = Template(type="am_critical", severity=Severity.critical,
                   title_template="{alertname} on {instance}", message_template="{summary}",
                   min_repeat_min=min_repeat_min, enabled=True)
    db_session.add_all([ch, tpl])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=tpl.id, channel_id=ch.id, severity_min=Severity.info, enabled=True))
    await db_session.commit()


async def _firing(db_session, fingerprint, **ctx):
    out = await fire_service.fire_episode(
        db_session, source_kind="alertmanager", source_key=f"am:1:{fingerprint}", name=ctx["alertname"],
        type="am_critical", context=ctx, source="alertmanager:prom",
    )
    await db_session.commit()
    return out


async def _delivered(db_session, incident_id):
    await fresh(db_session)
    return (await db_session.execute(select(func.count()).select_from(NotificationLog).where(
        NotificationLog.incident_id == incident_id, NotificationLog.suppressed_reason.is_(None)))).scalar_one()


async def _snooze_everything(db_session):
    db_session.add(Snooze(scope=SnoozeScope.type, target="*", until=utc_now() + timedelta(hours=1),
                          reason="maintenance", created_by="t"))
    await db_session.commit()


CTX = {"alertname": "DiskFull", "instance": "nas", "summary": "95%"}


async def test_alert_still_firing_after_the_snooze_ends_is_delivered(db_engine, db_session):
    await _setup(db_session)
    await _snooze_everything(db_session)
    first = await _firing(db_session, "f1", **CTX)
    assert first.episode == "opened"
    assert first.result.suppressed_reason == "snoozed"

    # Still snoozed: the repeat is suppressed again, and still nothing went out.
    during = await _firing(db_session, "f1", **CTX)
    assert during.episode == "repeat"
    assert during.result.suppressed_reason == "snoozed"
    assert await _delivered(db_session, first.incident_id) == 0

    # Maintenance is over, the disk is still full, Alertmanager re-sends the alert.
    await db_session.execute(delete(Snooze))
    await db_session.commit()
    after = await _firing(db_session, "f1", **CTX)
    assert after.episode == "repeat"
    assert after.incident_id == first.incident_id
    assert after.result.suppressed_reason is None
    assert await _delivered(db_session, first.incident_id) == 1

    # Announced now: further repeats notify nothing, as before.
    later = await _firing(db_session, "f1", **CTX)
    assert later.episode == "repeat"
    assert await _delivered(db_session, first.incident_id) == 1
    assert (await db_session.execute(select(func.count()).select_from(Incident))).scalar_one() == 1


async def test_second_alert_of_a_throttled_template_is_eventually_delivered(db_engine, db_session):
    # Two different alerts (fingerprints) map to one template with a cooldown.
    await _setup(db_session, min_repeat_min=1)
    a = await _firing(db_session, "f1", **CTX)
    b = await _firing(db_session, "f2", alertname="DiskFull", instance="db", summary="97%")
    assert a.result.suppressed_reason is None
    assert b.result.suppressed_reason == "throttled"

    # The cooldown passes (rewind the throttle state instead of sleeping).
    old = utc_now() - timedelta(minutes=10)
    await db_session.execute(update(ThrottleState).values(last_fired_at=old, reserved_at=old))
    await db_session.commit()

    again = await _firing(db_session, "f2", alertname="DiskFull", instance="db", summary="97%")
    assert again.episode == "repeat"
    assert await _delivered(db_session, b.incident_id) == 1
    assert await _delivered(db_session, a.incident_id) == 1   # the first alert was not sent twice


async def test_an_announced_episode_still_notifies_once(db_engine, db_session):
    await _setup(db_session)
    first = await _firing(db_session, "f1", **CTX)
    assert first.result.suppressed_reason is None
    for _ in range(3):
        again = await _firing(db_session, "f1", **CTX)
        assert again.episode == "repeat"
    assert await _delivered(db_session, first.incident_id) == 1
    await fresh(db_session)
    rows = (await db_session.execute(select(func.count()).select_from(NotificationLog))).scalar_one()
    assert rows == 1


async def test_repeats_during_a_snooze_do_not_pile_up_rows(db_engine, db_session):
    await _setup(db_session)
    await _snooze_everything(db_session)
    first = await _firing(db_session, "f1", **CTX)
    for _ in range(10):   # a source that repeats every few seconds
        await _firing(db_session, "f1", **CTX)
    await fresh(db_session)
    rows = (await db_session.execute(select(func.count()).select_from(NotificationLog).where(
        NotificationLog.incident_id == first.incident_id))).scalar_one()
    assert rows == 1, f"identical suppressed repeats must coalesce, got {rows} rows"
