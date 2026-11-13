"""Integration tests for the transactional outbox + retry worker (A01)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core import outbox
from app.core.delivery_worker import DeliveryWorker
from app.core.dispatcher import FireEnvelope, fire
from app.db.models import (
    ChannelKind,
    Delivery,
    DeliveryState,
    DeliveryStatus,
    NotificationLog,
    Severity,
    TemplateChannel,
)
from app.utils.time import utc_now


@pytest.fixture
async def template_with_channel(db_session, make_template, make_channel):
    t = make_template(min_repeat_min=0)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c.id, severity_min=Severity.info, enabled=True,
    ))
    await db_session.commit()
    await db_session.refresh(t)
    return t, c


def _retry_fail(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    async def inner():
        return DispatchOutcome(succeeded=[], failed={ch: "sink 503" for ch in channel_names})
    return inner()


def _ok(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    async def inner():
        return DispatchOutcome(succeeded=list(channel_names), failed={})
    return inner()


async def _deliveries(db_session, notif_id):
    return (
        await db_session.execute(select(Delivery).where(Delivery.notification_id == notif_id))
    ).scalars().all()


async def test_fire_persists_outbox_and_pends_on_retryable_fail(template_with_channel, db_session):
    """A retryable failure leaves the fire pending with a queued delivery —
    the record exists (persist-before-send) and will be retried."""
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(FireEnvelope(type=t.type, context={"k": 1}), db_session)
    await db_session.commit()

    assert r.status == "pending"
    row = (await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))).scalar_one()
    assert row.delivery_status == DeliveryStatus.pending
    ds = await _deliveries(db_session, r.id)
    assert len(ds) == 1
    assert ds[0].state == DeliveryState.pending
    assert ds[0].attempts == 1
    assert ds[0].next_attempt_at is not None


async def test_worker_delivers_a_pending_delivery(template_with_channel, db_session):
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(FireEnvelope(type=t.type, context={"k": 2}), db_session)
    await db_session.commit()

    # Make the pending delivery due now.
    d = (await _deliveries(db_session, r.id))[0]
    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    # Worker runs; this time delivery succeeds.
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        n = await DeliveryWorker()._process_due(db_session)
    assert n == 1

    d2 = (await _deliveries(db_session, r.id))[0]
    assert d2.state == DeliveryState.sent
    row = (await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))).scalar_one()
    assert row.delivery_status == DeliveryStatus.sent
    assert c.name in row.dispatched_to


async def test_retry_first_delivery_records_throttle_and_rule_count(
    template_with_channel, db_session, make_rule
):
    """F21: when a retry produces the first confirmed delivery, the worker
    must anchor the template throttle and bump the rule's lifetime counter —
    the synchronous path's bookkeeping, done exactly once."""
    from app.db.models import Rule, ThrottleState

    t, c = template_with_channel
    rule = make_rule(template_type=t.type, condition_expr="True", persist_n=1)
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    # Sync attempt fails → pending; no throttle anchored, counter untouched.
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(
            FireEnvelope(type=t.type, context={"k": 9}, rule_id=rule.id), db_session
        )
    await db_session.commit()
    assert (await db_session.get(Rule, rule.id)).fire_count_lifetime == 0
    assert (await db_session.execute(
        select(ThrottleState).where(ThrottleState.type == t.type)
    )).scalar_one_or_none() is None

    d = (await _deliveries(db_session, r.id))[0]
    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        await DeliveryWorker()._process_due(db_session)

    await db_session.refresh(rule)  # the UPDATE bumped the DB, refresh the ORM
    assert rule.fire_count_lifetime == 1
    ts = (await db_session.execute(
        select(ThrottleState).where(ThrottleState.type == t.type)
    )).scalar_one_or_none()
    assert ts is not None
    assert ts.last_fired_at is not None


async def test_partial_pending_rule_success_never_counted(
    db_session, make_template, make_channel, make_rule
):
    """V08: a rule fires to two channels; A delivers synchronously but B fails
    transiently, so the rollup stays *pending*. When B later succeeds on retry,
    the rule's lifetime counter must read exactly 1 — not 0.

    The audited code inferred "already counted?" from the channel list and the
    rollup status, which diverge in this scenario: the sync path skipped the
    count (status pending, not sent/partial) AND the retry skipped it too
    (channel A was already in dispatched_to, so ``was_delivered`` was true), so
    the fire was never counted anywhere. The idempotent ``success_counted`` CAS
    counts the first success wherever it lands, exactly once."""
    from app.db.models import Rule, ThrottleState

    t = make_template(min_repeat_min=0)
    a = make_channel(kind=ChannelKind.ui, name="chan_a")
    b = make_channel(kind=ChannelKind.ui, name="chan_b")
    db_session.add_all([t, a, b])
    await db_session.flush()
    db_session.add_all([
        TemplateChannel(
            template_id=t.id, channel_id=a.id, severity_min=Severity.info, enabled=True
        ),
        TemplateChannel(
            template_id=t.id, channel_id=b.id, severity_min=Severity.info, enabled=True
        ),
    ])
    rule = make_rule(template_type=t.type, condition_expr="True", persist_n=1)
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    def _a_ok_b_fail(self, notif, channel_names, session,
                     overrides_by_name=None, effective_by_name=None, **_kw):
        async def inner():
            succ = [ch for ch in channel_names if ch == "chan_a"]
            fail = {ch: "sink 503" for ch in channel_names if ch != "chan_a"}
            return DispatchOutcome(succeeded=succ, failed=fail)
        return inner()

    # Synchronous fire: A delivers, B fails → B pending, rollup not fully sent.
    with patch("app.channels.manager.ChannelManager.dispatch", new=_a_ok_b_fail):
        r = await fire(
            FireEnvelope(type=t.type, context={"k": 1}, rule_id=rule.id), db_session
        )
    await db_session.commit()

    row = (await db_session.execute(
        select(NotificationLog).where(NotificationLog.id == r.id)
    )).scalar_one()
    assert "chan_a" in row.dispatched_to
    assert row.delivery_status != DeliveryStatus.sent   # B still outstanding
    # The first success (A) is counted exactly once, at the sync dispatch.
    await db_session.refresh(rule)
    assert rule.fire_count_lifetime == 1

    # B's pending delivery becomes due; retry succeeds.
    b_deliv = [d for d in await _deliveries(db_session, r.id) if d.channel == "chan_b"]
    assert len(b_deliv) == 1
    b_deliv[0].next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        await DeliveryWorker()._process_due(db_session)

    # Both channels delivered now — still counted exactly once (no double-count).
    await db_session.refresh(rule)
    assert rule.fire_count_lifetime == 1
    ts = (await db_session.execute(
        select(ThrottleState).where(ThrottleState.type == t.type)
    )).scalar_one_or_none()
    assert ts is not None  # template throttle anchored exactly once


async def test_worker_skips_leased_delivery_then_claims_after_expiry(
    template_with_channel, db_session
):
    """F04: a delivery still leased by an in-flight attempt must not be
    re-sent even when its next_attempt_at is due; once the lease expires the
    worker claims and delivers it."""
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(FireEnvelope(type=t.type, context={"k": 11}), db_session)
    await db_session.commit()

    d = (await _deliveries(db_session, r.id))[0]
    # Due, but a concurrent attempt holds the lease (not yet settled).
    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    d.lease_until = utc_now() + timedelta(seconds=30)
    await db_session.commit()

    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        n = await DeliveryWorker()._process_due(db_session)
    assert n == 0  # leased row is skipped
    assert (await _deliveries(db_session, r.id))[0].state == DeliveryState.pending

    # Lease expires → the worker may claim and deliver it.
    d = (await _deliveries(db_session, r.id))[0]
    d.lease_until = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        n2 = await DeliveryWorker()._process_due(db_session)
    assert n2 == 1
    d2 = (await _deliveries(db_session, r.id))[0]
    assert d2.state == DeliveryState.sent
    assert d2.lease_until is None  # released on settle


async def test_first_attempt_still_duplicates_after_30sec(template_with_channel, db_session):
    """V03: a freshly-enqueued delivery whose synchronous first attempt is
    still in flight (attempts==0, pending, leased) must NOT be claimable by
    the worker when ``next_attempt_at`` comes due. Before the fix, enqueue set
    ``lease_until == next_attempt_at``, so both expired together at the grace
    boundary and the worker re-sent the still-in-flight row — a duplicate. The
    lease must outlast the grace window so the worker only takes over once the
    first attempt could no longer be running."""
    t, c = template_with_channel
    # Persist the durable intent exactly as the dispatcher does, WITHOUT
    # settling the first attempt — it is still in flight.
    enq = utc_now()
    log = NotificationLog(
        id="ntf_v03_inflight", type=t.type, severity=Severity.info,
        title="in flight", delivery_status=DeliveryStatus.pending,
        is_test=False, fired_at=enq, context_hash="v03hash",
    )
    db_session.add(log)
    await db_session.flush()
    outbox.enqueue(db_session, log.id, [c.name], now=enq)
    await db_session.commit()

    # Just past the 30s grace: next_attempt_at is due, but the first attempt
    # could still be sending, so the worker must skip the leased row.
    at_31s = enq + timedelta(seconds=31)
    with patch("app.core.delivery_worker.utc_now", return_value=at_31s), \
            patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        n = await DeliveryWorker()._process_due(db_session)
    assert n == 0, "worker re-sent a delivery whose first attempt is still in flight"
    d = (await _deliveries(db_session, log.id))[0]
    assert d.attempts == 0
    assert d.state == DeliveryState.pending


async def test_worker_terminal_failure_claim_returns_ghost_pending(
    template_with_channel, db_session
):
    """V04: when the worker exhausts retries and fails the notification, the
    admission claim (held since the fire) must be released so an identical
    in-window fire creates a FRESH notification. Before the fix only the
    dispatcher's synchronous-failure path released the claim; a delivery that
    failed terminally in the worker left the claim pointing at the dead id, so
    an identical fire coalesced onto it and returned 'pending' with no new
    delivery — a lost retry and a false state."""
    t, c = template_with_channel
    ctx = {"k": 404}
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(FireEnvelope(type=t.type, context=ctx), db_session)
    await db_session.commit()
    assert r.status == "pending"

    # Drive the delivery to its terminal failure through the real worker path.
    d = (await _deliveries(db_session, r.id))[0]
    d.attempts = outbox.MAX_ATTEMPTS - 1
    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    d.lease_until = None
    await db_session.commit()
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        await DeliveryWorker()._process_due(db_session)
    row = await db_session.get(NotificationLog, r.id)
    assert row.delivery_status == DeliveryStatus.failed  # terminal

    # An identical fire within the window must NOT ghost-coalesce onto the
    # dead id; it must mint a fresh notification and actually dispatch.
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        r2 = await fire(FireEnvelope(type=t.type, context=ctx), db_session)
    await db_session.commit()
    assert r2.id != r.id, "identical fire ghost-coalesced onto the failed notification"
    assert len(await _deliveries(db_session, r2.id)) == 1


async def test_per_delivery_commit_isolates_a_failing_row(template_with_channel, db_session):
    """R05: the worker commits per delivery, so a crash/exception on one row
    doesn't roll back the earlier settled rows of the batch."""
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r1 = await fire(FireEnvelope(type=t.type, context={"k": 51}), db_session)
        await db_session.commit()
        r2 = await fire(FireEnvelope(type=t.type, context={"k": 52}), db_session)
        await db_session.commit()

    for r in (r1, r2):
        d = (await _deliveries(db_session, r.id))[0]
        d.next_attempt_at = utc_now() - timedelta(seconds=1)
        d.lease_until = None
    await db_session.commit()

    calls = {"n": 0}

    def _flaky(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        async def inner():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom on first")
            return DispatchOutcome(succeeded=list(channel_names), failed={})
        return inner()

    with patch("app.channels.manager.ChannelManager.dispatch", new=_flaky):
        processed = await DeliveryWorker()._process_due(db_session)

    assert processed == 1  # the second delivery settled; the first rolled back
    all_d = (await _deliveries(db_session, r1.id)) + (await _deliveries(db_session, r2.id))
    states = sorted(d.state for d in all_d)
    assert states == [DeliveryState.pending, DeliveryState.sent]


async def test_worker_skips_not_due_deliveries(template_with_channel, db_session):
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(FireEnvelope(type=t.type, context={"k": 3}), db_session)
    await db_session.commit()
    # next_attempt_at is in the future (initial grace) → worker does nothing.
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        n = await DeliveryWorker()._process_due(db_session)
    assert n == 0
    assert (await _deliveries(db_session, r.id))[0].state == DeliveryState.pending


async def test_worker_marks_failed_on_permanent_error(template_with_channel, db_session):
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(FireEnvelope(type=t.type, context={"k": 4}), db_session)
    await db_session.commit()
    d = (await _deliveries(db_session, r.id))[0]
    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    def _perm(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        async def inner():
            return DispatchOutcome(succeeded=[], failed={ch: "channel disabled" for ch in channel_names})
        return inner()

    with patch("app.channels.manager.ChannelManager.dispatch", new=_perm):
        await DeliveryWorker()._process_due(db_session)
    d2 = (await _deliveries(db_session, r.id))[0]
    assert d2.state == DeliveryState.failed
    row = (await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))).scalar_one()
    assert row.delivery_status == DeliveryStatus.failed


# ── F03: retries use the destination captured at enqueue ──────────


async def test_retry_uses_stored_route_override(db_engine, db_session, make_template, make_channel):
    """A retry must deliver to the SAME destination as the first attempt
    (the per-route override captured at enqueue), not the channel's
    current base config (audit F03)."""
    t = make_template(min_repeat_min=0)
    c = make_channel(kind=ChannelKind.ui, name="ovc")
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c.id, severity_min=Severity.info,
        enabled=True, channel_overrides={"recipient": "team_B"},
    ))
    await db_session.commit()

    captured: dict = {}

    def _fail_capture(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        async def inner():
            captured["first"] = effective_by_name
            return DispatchOutcome(succeeded=[], failed={ch: "sink 503" for ch in channel_names})
        return inner()

    with patch("app.channels.manager.ChannelManager.dispatch", new=_fail_capture):
        r = await fire(FireEnvelope(type=t.type, context={}), db_session)
    await db_session.commit()

    # The override is captured on the delivery row, and the full effective
    # destination (base merged with the override) is frozen for retries (V01).
    d = (await _deliveries(db_session, r.id))[0]
    assert d.channel_overrides == {"recipient": "team_B"}
    assert d.effective_config == {"recipient": "team_B"}

    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    def _ok_capture(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        async def inner():
            captured["retry"] = effective_by_name
            return DispatchOutcome(succeeded=list(channel_names), failed={})
        return inner()

    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok_capture):
        await DeliveryWorker()._process_due(db_session)

    # The retry delivered with the frozen effective destination (V01), not an
    # empty/base config and not a live re-read of the channel.
    assert captured["retry"] == {c.name: {"recipient": "team_B"}}


def _raise(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    # Simulate a bug in delivery processing (not a normal send failure): dispatch
    # itself throws, so the worker's except path runs.
    raise RuntimeError("kaboom in dispatch")


async def test_worker_exception_consumes_an_attempt(template_with_channel, db_session):
    """C-11: a delivery whose processing THROWS must still consume an attempt, so
    a persistently-broken row eventually goes terminal instead of being reclaimed
    and re-thrown forever with its attempt count frozen."""
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_retry_fail):
        r = await fire(FireEnvelope(type=t.type, context={"k": 9}), db_session)
    await db_session.commit()

    d = (await _deliveries(db_session, r.id))[0]
    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    before = d.attempts

    with patch("app.channels.manager.ChannelManager.dispatch", new=_raise):
        await DeliveryWorker()._process_due(db_session)

    d2 = (await _deliveries(db_session, r.id))[0]
    assert d2.attempts == before + 1, "the exception path must consume an attempt"
    # And it is left retryable (pending) with a backoff, not stuck unleased.
    assert d2.lease_until is None
