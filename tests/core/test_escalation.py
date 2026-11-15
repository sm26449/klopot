"""Tests for app.core.escalation — re-page unacked criticals."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core import outbox
from app.core.delivery_worker import DeliveryWorker
from app.core.escalation import EscalationService
from app.db.models import Delivery, DeliveryState, DeliveryStatus, NotificationLog, Severity
from app.utils.time import utc_now


def _row(
    *,
    id_: str,
    severity: Severity = Severity.critical,
    age_min: int = 30,
    acknowledged: bool = False,
    escalated: bool = False,
    is_test: bool = False,
    suppressed=None,
) -> NotificationLog:
    now = utc_now()
    return NotificationLog(
        id=id_,
        type="t_esc",
        severity=severity,
        title=f"critical {id_}",
        message="boom",
        vars_payload={},
        dispatched_to=["telegram_main"],
        delivery_status=DeliveryStatus.sent,
        failed_channels={},
        suppressed_reason=suppressed,
        fired_at=now - timedelta(minutes=age_min),
        acknowledged_at=(now - timedelta(minutes=5)) if acknowledged else None,
        escalated_at=(now - timedelta(minutes=5)) if escalated else None,
        is_test=is_test,
    )


@pytest.fixture
def fake_manager():
    mgr = AsyncMock()
    mgr.dispatch = AsyncMock(
        return_value=DispatchOutcome(succeeded=["sms_main"], failed={})
    )
    return mgr


async def _sweep(fake_manager) -> int:
    svc = EscalationService()
    with patch(
        "app.channels.manager.get_channel_manager", return_value=fake_manager
    ):
        return await svc.sweep_once()


async def _make_due(db_session):
    """Use an explicit past time: MySQL DATETIME rounds fractional seconds.

    Commit also ends the reader's repeatable-read snapshot before a fresh
    worker session processes these rows.
    """
    ds = (await db_session.execute(
        select(Delivery).where(Delivery.state == DeliveryState.pending)
    )).scalars().all()
    for d in ds:
        d.next_attempt_at = utc_now() - timedelta(seconds=2)
    await db_session.commit()


async def test_escalates_old_unacked_critical(db_session, fake_manager):
    db_session.add(_row(id_="n1", age_min=30))
    await db_session.commit()

    n = await _sweep(fake_manager)

    assert n == 1
    fake_manager.dispatch.assert_not_awaited()
    delivery = (await db_session.execute(select(Delivery))).scalar_one()
    assert delivery.channel == "sms_main"
    assert delivery.purpose == "escalation"
    assert delivery.state == DeliveryState.pending
    assert delivery.attempts == 0
    assert delivery.lease_until is None
    row = (
        await db_session.execute(
            select(NotificationLog).where(NotificationLog.id == "n1")
        )
    ).scalar_one()
    assert row.escalated_at is not None


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"acknowledged": True}, "acked"),
        ({"escalated": True}, "already escalated"),
        ({"is_test": True}, "test fire"),
        ({"severity": Severity.warning}, "not critical"),
        ({"age_min": 5}, "younger than escalation_after_min"),
        ({"age_min": 60 * 25}, "older than 24h backstop"),
    ],
)
async def test_not_escalated(db_session, fake_manager, kwargs, why):
    db_session.add(_row(id_="n2", **kwargs))
    await db_session.commit()

    n = await _sweep(fake_manager)

    assert n == 0, f"should skip: {why}"
    fake_manager.dispatch.assert_not_awaited()


async def test_suppressed_row_not_escalated(db_session, fake_manager):
    from app.db.models import SuppressedReason

    db_session.add(_row(id_="n3", suppressed=SuppressedReason.throttled))
    await db_session.commit()
    assert await _sweep(fake_manager) == 0


async def test_retry_survives_new_worker_and_preserves_original(db_session, fake_manager):
    """One durable escalation, retried independently from the original fire."""
    fake_manager.dispatch = AsyncMock(
        return_value=DispatchOutcome(succeeded=[], failed={"sms_main": "down"})
    )
    db_session.add(_row(id_="n4", age_min=30))
    await db_session.commit()

    assert await _sweep(fake_manager) == 1
    row = (
        await db_session.execute(
            select(NotificationLog).where(NotificationLog.id == "n4")
        )
    ).scalar_one()
    assert row.escalated_at is not None
    assert await _sweep(fake_manager) == 0
    assert len((await db_session.execute(select(Delivery))).scalars().all()) == 1

    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    fake_manager.dispatch.assert_awaited_once()
    first_notif = fake_manager.dispatch.await_args.args[0]
    assert first_notif.title.startswith("ESCALATION (unacked")
    d = (await db_session.execute(select(Delivery))).scalar_one()
    await db_session.refresh(d)
    assert d.attempts == 1
    assert d.state == DeliveryState.pending
    assert d.next_attempt_at > utc_now()
    assert d.idempotency_key == f"{first_notif.id}:sms_main"
    d.next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    fake_manager.dispatch.return_value = DispatchOutcome(succeeded=["sms_main"])
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    assert fake_manager.dispatch.await_args.args[0] == first_notif
    await db_session.refresh(d)
    await db_session.refresh(row)
    assert d.attempts == 2
    assert d.state == DeliveryState.sent
    assert d.next_attempt_at is None
    assert row.delivery_status == DeliveryStatus.sent
    assert row.dispatched_to == ["telegram_main"]
    assert row.failed_channels == {}
    assert row.success_counted is False


async def test_escalation_exhausts_bounded_retries(db_session, fake_manager):
    db_session.add(_row(id_="bounded"))
    await db_session.commit()
    await _sweep(fake_manager)
    fake_manager.dispatch.return_value = DispatchOutcome(failed={"sms_main": "sink 503"})
    d = (await db_session.execute(select(Delivery))).scalar_one()
    for _ in range(outbox.MAX_ATTEMPTS):
        d.next_attempt_at = utc_now() - timedelta(seconds=1)
        await db_session.commit()
        with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
            assert await DeliveryWorker().tick() == 1
        await db_session.refresh(d)
    assert d.state == DeliveryState.failed
    assert d.attempts == outbox.MAX_ATTEMPTS
    assert d.last_error == "sink 503"
    assert d.next_attempt_at is None
    assert await _sweep(fake_manager) == 0
    assert await DeliveryWorker().tick() == 0


async def test_ack_stops_worker_after_expired_lease(db_session, fake_manager):
    db_session.add(_row(id_="acked_after_queue"))
    await db_session.commit()
    await _sweep(fake_manager)
    row = await db_session.get(NotificationLog, "acked_after_queue")
    row.acknowledged_at = utc_now()
    d = (await db_session.execute(select(Delivery))).scalar_one()
    d.lease_until = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    fake_manager.dispatch.assert_not_awaited()
    await db_session.refresh(d)
    assert d.state == DeliveryState.cancelled
    assert d.attempts == 0
    assert d.next_attempt_at is None
    assert d.lease_until is None


async def test_enqueue_and_stamp_roll_back_together(db_session):
    row = _row(id_="atomic")
    db_session.add(row)
    await db_session.commit()
    assert await EscalationService()._escalate(row, db_session)
    await db_session.flush()
    await db_session.rollback()
    row = await db_session.get(NotificationLog, "atomic")
    assert row.escalated_at is None
    assert (await db_session.execute(select(Delivery))).scalars().all() == []


async def test_escalation_uses_frozen_channel_and_coexists_with_initial(
    db_session, fake_manager, make_channel,
):
    c = make_channel(name="sms_main", config={"destination": "original"})
    row = _row(id_="same_channel")
    db_session.add_all([row, c])
    await db_session.flush()
    initial = outbox.enqueue(db_session, row.id, [c.name])[0]
    initial.state = DeliveryState.sent
    initial.next_attempt_at = None
    initial.lease_until = None
    await db_session.commit()
    await _sweep(fake_manager)
    c.config = {"destination": "changed"}
    await db_session.commit()

    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    kw = fake_manager.dispatch.await_args.kwargs
    assert kw["effective_by_name"] == {"sms_main": {"destination": "original"}}
    assert kw["effective_kind_by_name"] == {"sms_main": "ui"}
    ds = (await db_session.execute(select(Delivery))).scalars().all()
    assert len(ds) == 2
    assert len({d.idempotency_key for d in ds}) == 2


async def test_worker_exception_does_not_rewrite_initial_status(db_session, fake_manager):
    db_session.add(_row(id_="exception"))
    await db_session.commit()
    await _sweep(fake_manager)
    fake_manager.dispatch.side_effect = RuntimeError("unexpected")
    d = (await db_session.execute(select(Delivery))).scalar_one()
    d.attempts = outbox.MAX_ATTEMPTS - 1
    await db_session.commit()
    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        await DeliveryWorker().tick()
    await db_session.refresh(d)
    row = await db_session.get(NotificationLog, "exception")
    await db_session.refresh(row)
    assert d.state == DeliveryState.failed
    assert row.delivery_status == DeliveryStatus.sent
    assert row.dispatched_to == ["telegram_main"]


async def test_old_queued_escalation_expires_without_sending(db_session, fake_manager):
    db_session.add(_row(id_="expired"))
    await db_session.commit()
    await _sweep(fake_manager)
    d = (await db_session.execute(select(Delivery))).scalar_one()
    d.created_at = utc_now() - timedelta(seconds=outbox.MAX_DELIVERY_AGE_SEC + 1)
    await db_session.commit()
    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    fake_manager.dispatch.assert_not_awaited()
    await db_session.refresh(d)
    assert d.state == DeliveryState.failed
    assert d.attempts == 0
    assert d.last_error == "escalation expired before delivery"


async def test_deferred_escalation_does_not_spend_transport_attempt(db_session, fake_manager):
    db_session.add(_row(id_="deferred"))
    await db_session.commit()
    await _sweep(fake_manager)
    fake_manager.dispatch.return_value = DispatchOutcome(deferred={"sms_main": "circuit_open"})
    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    d = (await db_session.execute(select(Delivery))).scalar_one()
    assert d.state == DeliveryState.pending
    assert d.attempts == 0
    assert d.next_attempt_at > utc_now()


@pytest.mark.parametrize(("scope", "target"), [
    ("type", "t_esc"), ("type", "*"), ("channel", "sms_main"), ("rule", "201"),
])
async def test_explicit_snooze_pauses_queue_and_resumes_after_expiry(db_session, fake_manager, scope, target):
    from app.db.models import Rule, Snooze, SnoozeScope

    rule = Rule(id=201, name="snoozed_rule", template_type="t_esc", condition_expr="True")
    db_session.add(rule)
    await db_session.flush()
    row = _row(id_="snooze_before_queue")
    row.rule_id = rule.id
    snooze = Snooze(scope=SnoozeScope(scope), target=target, until=utc_now() + timedelta(hours=1))
    db_session.add_all([row, snooze])
    await db_session.commit()
    assert await _sweep(fake_manager) == 0
    snooze.until = utc_now() - timedelta(seconds=2)
    await db_session.commit()
    assert await _sweep(fake_manager) == 1
    # A new snooze committed after enqueue must also stop the queued worker.
    snooze.until = utc_now() + timedelta(hours=1)
    await db_session.commit()
    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    fake_manager.dispatch.assert_not_awaited()
    delivery = (await db_session.execute(select(Delivery))).scalar_one()
    assert delivery.state == DeliveryState.pending
    assert delivery.attempts == 0
    assert delivery.last_error == "deferred: snoozed"
    snooze.until = utc_now() - timedelta(seconds=2)
    await db_session.commit()
    await _make_due(db_session)
    with patch("app.channels.manager.get_channel_manager", return_value=fake_manager):
        assert await DeliveryWorker().tick() == 1
    fake_manager.dispatch.assert_awaited_once()
    await db_session.refresh(delivery)
    assert delivery.state == DeliveryState.sent


@pytest.mark.mysql
async def test_concurrent_sweeps_queue_exactly_one_escalation(db_session):
    import asyncio

    db_session.add(_row(id_="concurrent"))
    await db_session.commit()
    results = await asyncio.gather(
        EscalationService().sweep_once(), EscalationService().sweep_once(),
    )
    assert sum(results) == 1
    ds = (await db_session.execute(select(Delivery))).scalars().all()
    assert len(ds) == 1
    assert ds[0].purpose == "escalation"


async def test_disabled_when_after_min_zero(db_session, fake_manager):
    from app.config import get_settings

    db_session.add(_row(id_="n5", age_min=30))
    await db_session.commit()
    settings = get_settings()
    old = settings.escalation_after_min
    object.__setattr__(settings, "escalation_after_min", 0)
    try:
        assert await _sweep(fake_manager) == 0
    finally:
        object.__setattr__(settings, "escalation_after_min", old)

async def test_disabled_when_channel_empty(db_session, fake_manager):
    """C-08: with no escalation channel configured, the sweep does nothing
    instead of trying to dispatch to a missing channel."""
    from app.config import get_settings

    db_session.add(_row(id_="n6", age_min=30))
    await db_session.commit()
    settings = get_settings()
    old = settings.escalation_channel
    object.__setattr__(settings, "escalation_channel", "")
    try:
        assert await _sweep(fake_manager) == 0
    finally:
        object.__setattr__(settings, "escalation_channel", old)
