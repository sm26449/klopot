"""External episodes: POST /v1/fire with idempotency_key, and the shared
fire service (app/core/fire_service.py)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core import fire_service
from app.db.models import Incident, NotificationLog, Severity, Template, TemplateChannel
from tests._db import fresh


@pytest.fixture
async def templates(db_session, make_channel):
    """Both templates routed to a UI channel: a recovery notice goes out only
    for an episode someone was told about."""
    rows = [
        Template(type="disk_full", severity=Severity.critical, title_template="Disk full on {host}", min_repeat_min=0),
        Template(type="disk_ok", severity=Severity.info, title_template="Disk OK on {host}", min_repeat_min=0),
    ]
    channel = make_channel(name="episodes_ui", rate_limit_per_min=1000)
    db_session.add_all([*rows, channel])
    await db_session.flush()
    db_session.add_all(TemplateChannel(template_id=t.id, channel_id=channel.id, enabled=True,
                                       severity_min=Severity.info) for t in rows)
    await db_session.commit()


async def _fire(client, key, **body):
    r = await client.post("/v1/fire", json=body, headers={"X-API-Key": key})
    assert r.status_code == 202, r.text
    return r.json()


async def _count(db_session, model, *where):
    await fresh(db_session)
    return (await db_session.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_episode_open_repeat_resolve(db_client, db_session, admin_key, templates):
    base = {"type": "disk_full", "context": {"host": "nas"}, "idempotency_key": "nas-disk",
            "resolved_type": "disk_ok"}
    first = await _fire(db_client, admin_key, **base)
    assert first["episode"] == "opened" and first["incident_id"].startswith("inc_")
    assert first["title"] == "Disk full on nas"

    again = await _fire(db_client, admin_key, **base)
    assert again["episode"] == "repeat"
    assert again["incident_id"] == first["incident_id"]
    assert again["id"] == first["id"], "a repeat points at the episode's notification"
    assert await _count(db_session, NotificationLog, NotificationLog.type == "disk_full") == 1

    done = await _fire(db_client, admin_key, type="disk_full", context={"host": "nas"},
                       idempotency_key="nas-disk", status="resolved")
    assert done["episode"] == "resolved"
    assert done["title"] == "Disk OK on nas", "resolution notice sent"
    await fresh(db_session)
    inc = await db_session.get(Incident, first["incident_id"])
    await db_session.refresh(inc)
    assert inc.resolved_at is not None and inc.active_source_key is None
    assert inc.source_kind == "fire" and inc.source_key.endswith(":nas-disk")

    # The key is free again: a new firing opens a new episode.
    reopened = await _fire(db_client, admin_key, **base)
    assert reopened["episode"] == "opened" and reopened["incident_id"] != first["incident_id"]


async def test_resolve_without_episode_and_without_key(db_client, admin_key, templates):
    r = await _fire(db_client, admin_key, type="disk_full", context={}, idempotency_key="never", status="resolved")
    assert r["episode"] == "not_found" and r["dispatched"] is False
    bad = await db_client.post("/v1/fire", json={"type": "disk_full", "status": "resolved"},
                               headers={"X-API-Key": admin_key})
    assert bad.status_code == 422


async def test_an_episode_nobody_was_told_about_closes_without_a_recovery_notice(
        db_client, db_session, admin_key, templates):
    # The failure reached no channel (here: no route; equally snoozed, quiet
    # hours, throttled, failed everywhere): its end is not news.
    db_session.add(Template(type="nas_fan", severity=Severity.warning, title_template="Fan {host}", min_repeat_min=0))
    await db_session.commit()
    opened = await _fire(db_client, admin_key, type="nas_fan", context={"host": "nas"},
                         idempotency_key="nas-fan", resolved_type="disk_ok")
    assert opened["episode"] == "opened" and opened["dispatched"] is False
    done = await _fire(db_client, admin_key, type="nas_fan", context={"host": "nas"},
                       idempotency_key="nas-fan", status="resolved")
    assert done["episode"] == "resolved" and done["dispatched"] is False and done["title"] == ""
    assert await _count(db_session, NotificationLog, NotificationLog.type == "disk_ok") == 0
    assert await _count(db_session, Incident, Incident.resolved_at.is_not(None)) == 1


async def test_test_fires_ignore_the_key_and_unknown_types_open_nothing(db_client, db_session, admin_key, templates):
    r = await _fire(db_client, admin_key, type="disk_full", context={"host": "x"}, idempotency_key="k1", test=True)
    assert r["episode"] is None
    r = await _fire(db_client, admin_key, type="no_such_type", context={}, idempotency_key="k2")
    assert r["suppressed_reason"] == "unknown_type" and r["incident_id"] is None
    assert await _count(db_session, Incident) == 0


async def test_keys_are_scoped_to_the_caller(db_session, templates):
    a = await fire_service.fire_episode(db_session, source_kind="fire", source_key="fire:a:k", name="k",
                                        type="disk_full", context={"host": "a"}, source="a")
    b = await fire_service.fire_episode(db_session, source_kind="fire", source_key="fire:b:k", name="k",
                                        type="disk_full", context={"host": "b"}, source="b")
    await db_session.commit()
    assert a.episode == b.episode == "opened" and a.incident_id != b.incident_id


async def test_newer_start_supersedes_and_stale_resolve_is_ignored(db_session, templates):
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    key = "am:1:abc"
    first = await fire_service.fire_episode(db_session, source_kind="alertmanager", source_key=key, name="DiskFull",
                                            type="disk_full", context={"host": "n"}, source="am", started_at=t0)
    same = await fire_service.fire_episode(db_session, source_kind="alertmanager", source_key=key, name="DiskFull",
                                           type="disk_full", context={"host": "n"}, source="am", started_at=t0)
    assert (first.episode, same.episode) == ("opened", "repeat")
    newer = await fire_service.fire_episode(db_session, source_kind="alertmanager", source_key=key, name="DiskFull",
                                            type="disk_full", context={"host": "n"}, source="am",
                                            started_at=t0 + timedelta(hours=1))
    assert newer.episode == "opened" and newer.incident_id != first.incident_id
    old = await db_session.get(Incident, first.incident_id)
    assert old.resolution_reason == "superseded"

    stale = await fire_service.resolve_episode(db_session, source_key=key, context={}, started_at=t0)
    assert stale.episode == "stale"
    current = await db_session.get(Incident, newer.incident_id)
    assert current.resolved_at is None
    done = await fire_service.resolve_episode(db_session, source_key=key, context={},
                                              started_at=t0 + timedelta(hours=1))
    assert done.episode == "resolved"
    await db_session.commit()


@pytest.mark.mysql
async def test_concurrent_first_fires_open_one_episode(db_session, templates):
    """Two simultaneous first fires of one key (e.g. two Alertmanager replicas):
    the unique active_source_key lets one open the episode; the other turns
    into a repeat — one incident, one notification."""
    import asyncio

    from app.db.session import get_session_factory

    async def one():
        async with get_session_factory()() as session:
            out = await fire_service.fire_episode(
                session, source_kind="alertmanager", source_key="am:1:race", name="Race",
                type="disk_full", context={"host": "r"}, source="am")
            await session.commit()
            return out.episode

    episodes = sorted(await asyncio.gather(one(), one()))
    assert episodes == ["opened", "repeat"]
    assert await _count(db_session, Incident) == 1
    assert await _count(db_session, NotificationLog) == 1
