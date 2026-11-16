"""Independent-session concurrency tests — MySQL only (CI MySQL gate).

These race two genuinely separate sessions on separate connections, so they
need a database with real row-level locking. SQLite (single writer, in-memory
test harness) can't express the race, so they are marked ``mysql`` and skipped
on the SQLite run. They guard the two hardening invariants the audit added:

- R01: concurrent fires of the same context coalesce to ONE notification
  (the atomic admission claim serialises them).
- F04: concurrent workers claiming the same due delivery send it ONCE (the
  lease compare-and-set lets exactly one win).
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core.delivery_worker import DeliveryWorker
from app.core.dispatcher import FireEnvelope, fire
from app.db.models import ChannelKind, Delivery, NotificationLog, Severity, TemplateChannel
from app.utils.time import utc_now

pytestmark = pytest.mark.mysql


async def _ok(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    return DispatchOutcome(succeeded=list(channel_names), failed={})


async def _retry_fail(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    return DispatchOutcome(succeeded=[], failed={c: "sink 503" for c in channel_names})


async def _seed_template(db_session, make_template, make_channel):
    t = make_template(min_repeat_min=0)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c.id, severity_min=Severity.info, enabled=True,
    ))
    await db_session.commit()
    return t, c


async def test_concurrent_fires_coalesce_to_one(db_session, make_template, make_channel):
    """R01: two sessions fire the identical context at once — the admission
    claim serialises them, so exactly one notification is created and both
    callers get its id."""
    from app.db import session as session_module

    t, _ = await _seed_template(db_session, make_template, make_channel)
    env = FireEnvelope(type=t.type, context={"k": "race"})

    async def one():
        async with session_module._session_factory() as s:
            r = await fire(env, s)
            await s.commit()
            return r

    # Patch ONCE around the gather, never inside the concurrent coroutines:
    # two overlapping `with patch(...)` on the same global corrupt the restore
    # and leak the mock into later tests.
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        r1, r2 = await asyncio.gather(one(), one())

    assert r1.id == r2.id, "concurrent identical fires must coalesce to one id"
    async with session_module._session_factory() as s:
        rows = (await s.execute(
            select(NotificationLog).where(NotificationLog.type == t.type)
        )).scalars().all()
    assert len(rows) == 1, f"expected one notification, got {len(rows)}"


async def test_concurrent_workers_claim_lease_once(db_session, make_template, make_channel):
    """F04: a pending delivery becomes due; two workers process concurrently.
    The lease compare-and-set lets exactly one claim and send it — the other
    sees it leased and skips, so the channel is dispatched once."""
    from app.db import session as session_module

    t, _ = await _seed_template(db_session, make_template, make_channel)

    # First (sync) attempt fails retryably → one pending delivery.
    async with session_module._session_factory() as s:
        with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
            r = await fire(FireEnvelope(type=t.type, context={"k": "lease"}), s)
        await s.commit()

    # Make it due now.
    async with session_module._session_factory() as s:
        d = (await s.execute(
            select(Delivery).where(Delivery.notification_id == r.id)
        )).scalar_one()
        d.next_attempt_at = utc_now() - timedelta(seconds=1)
        await s.commit()

    sends: list[int] = []

    async def _ok_counting(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        sends.append(1)
        return DispatchOutcome(succeeded=list(channel_names), failed={})

    async def work():
        async with session_module._session_factory() as s:
            n = await DeliveryWorker()._process_due(s)
            await s.commit()
            return n

    # Patch ONCE around the gather (see the note in the dedup test above).
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok_counting):
        n1, n2 = await asyncio.gather(work(), work())

    assert n1 + n2 == 1, f"exactly one worker should process the delivery (got {n1}+{n2})"
    assert len(sends) == 1, f"the channel must be dispatched once (got {len(sends)})"


async def test_concurrent_distinct_fires_of_one_type_all_land(db_session, make_template, make_channel):
    """P01: parallel fires of ONE type with DIFFERENT contexts must not block
    each other. The claim read-back used ``is_test IS false``, which MySQL
    cannot use as a key equality: the lookup scanned — and ``FOR UPDATE``
    locked — every claim of the type, so two fires deadlocked (error 1213) and
    the loser's alert was rolled back, neither stored nor sent."""
    from app.db import session as session_module

    t, _ = await _seed_template(db_session, make_template, make_channel)

    async def one(i: int):
        async with session_module._session_factory() as s:
            r = await fire(FireEnvelope(type=t.type, context={"k": f"distinct-{i}"}), s)
            await s.commit()
            return r.id

    rounds, width = 5, 8
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        ids: list[str] = []
        for n in range(rounds):
            ids += await asyncio.gather(*(one(n * width + i) for i in range(width)))

    assert len(set(ids)) == rounds * width, "every distinct fire gets its own notification"
    async with session_module._session_factory() as s:
        rows = (await s.execute(
            select(NotificationLog.id).where(NotificationLog.type == t.type)
        )).scalars().all()
    assert len(rows) == rounds * width, f"expected {rounds * width} stored notifications, got {len(rows)}"
