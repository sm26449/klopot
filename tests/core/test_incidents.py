"""Incident transitions driven by real engine evaluations and durable outbox rows."""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core import incidents, outbox
from app.core.delivery_worker import DeliveryWorker
from app.core.engine import RuleEngine
from app.core.escalation import EscalationService
from app.core.state_cache import StateCache
from app.channels.manager import DispatchOutcome
from app.db import get_session_factory
from app.db.models import Delivery, DeliveryState, DeliveryStatus, Incident, NotificationLog, Rule, Severity, TemplateChannel
from app.utils.time import utc_now


@pytest.fixture
async def scenario(db_session, make_rule, make_template, make_channel):
    firing = make_template(type="overheat", severity=Severity.critical, min_repeat_min=0,
                           title_template="Too hot: {x}")
    recovery = make_template(type="temperature_normal", severity=Severity.info, min_repeat_min=0,
                             title_template="Normal: {x}", message_template="Duration {_incident.duration_sec}s")
    channel = make_channel(name="incident_ui", rate_limit_per_min=1000)
    rule = make_rule(template_type=firing.type, condition_expr="x > 80", persist_n=2,
                     incident_enabled=True, recovery_expr="x < 75", recovery_persist_n=2,
                     resolved_template_type=recovery.type)
    db_session.add_all([firing, recovery, channel, rule])
    await db_session.flush()
    for template in (firing, recovery):
        db_session.add(TemplateChannel(template_id=template.id, channel_id=channel.id, enabled=True,
                                       severity_min=Severity.info))
    await db_session.commit()
    engine = RuleEngine()
    engine._cache = StateCache()
    await engine.reload_rules()
    return engine, rule.id


async def evaluate(engine, rule_id, value):
    await engine._cache.set("x", value)
    await engine._eval_rule(engine._rules[rule_id], now=time.monotonic())


async def read_all(model):
    async with get_session_factory()() as session:
        return list((await session.execute(select(model))).scalars().all())


async def open_problem(scenario):
    engine, rule_id = scenario
    await evaluate(engine, rule_id, 90)
    await evaluate(engine, rule_id, 90)
    return (await read_all(Incident))[0]


async def test_open_requires_persistence_and_never_sends_before_commit(scenario):
    engine, rule_id = scenario
    with patch("app.channels.manager.ChannelManager.dispatch", new_callable=AsyncMock) as send:
        await evaluate(engine, rule_id, 90)
        assert await read_all(Incident) == []
        await evaluate(engine, rule_id, 90)
        send.assert_not_awaited()
    [incident] = await read_all(Incident)
    [log] = await read_all(NotificationLog)
    [delivery] = await read_all(Delivery)
    assert incident.state == "active"
    assert incident.acknowledged_at is None
    assert log.incident_id == incident.id
    assert log.incident_event == "firing"
    assert log.delivery_status == DeliveryStatus.pending
    assert delivery.state == DeliveryState.pending
    assert delivery.attempts == 0
    assert delivery.lease_until is None


async def test_hysteresis_recovery_is_separate_from_ack_and_cancels_old_pages(scenario):
    engine, rule_id = scenario
    original = await open_problem(scenario)
    await evaluate(engine, rule_id, 78)  # inside hysteresis band
    assert (await read_all(Incident))[0].state == "active"
    assert engine._last_truthy[original.rule_name] is not None
    await evaluate(engine, rule_id, 70)
    assert (await read_all(Incident))[0].state == "active"
    await evaluate(engine, rule_id, 70)
    [incident] = await read_all(Incident)
    assert incident.state == "resolved"
    assert incident.resolution_reason == "recovered"
    assert incident.acknowledged_at is None
    assert incident.active_rule_id is None
    logs = {r.incident_event: r for r in await read_all(NotificationLog)}
    assert logs["firing"].delivery_status == DeliveryStatus.cancelled
    assert logs["resolved"].delivery_status == DeliveryStatus.pending
    assert logs["resolved"].title == "Normal: 70"
    assert logs["resolved"].vars_payload["_incident"]["id"] == incident.id
    assert "duration_sec" in logs["resolved"].vars_payload["_incident"]
    assert original.rule_name not in engine._last_truthy
    await evaluate(engine, rule_id, 70)
    await evaluate(engine, rule_id, 70)
    assert len(await read_all(NotificationLog)) == 2


async def test_unknown_and_stale_data_never_resolve_and_break_recovery_streak(scenario):
    engine, rule_id = scenario
    await open_problem(scenario)
    await evaluate(engine, rule_id, 70)
    assert engine._rules[rule_id].recovery_match_count == 1
    engine._cache._values.clear()
    await engine._eval_rule(engine._rules[rule_id], now=time.monotonic())
    assert engine._rules[rule_id].recovery_match_count == 0
    assert (await read_all(Incident))[0].state == "active"
    await evaluate(engine, rule_id, 70)
    assert (await read_all(Incident))[0].state == "active"
    await evaluate(engine, rule_id, 70)
    assert (await read_all(Incident))[0].state == "resolved"


async def test_restart_restores_episode_and_recovery_counter(scenario):
    engine, rule_id = scenario
    original = await open_problem(scenario)
    await evaluate(engine, rule_id, 70)
    restarted = RuleEngine()
    restarted._cache = engine._cache
    await restarted.reload_rules()
    assert restarted._rules[rule_id].recovery_match_count == 1
    await evaluate(restarted, rule_id, 70)
    [incident] = await read_all(Incident)
    assert incident.id == original.id
    assert incident.state == "resolved"
    await evaluate(restarted, rule_id, 90)
    await evaluate(restarted, rule_id, 90)
    episodes = await read_all(Incident)
    assert len(episodes) == 2
    assert sum(i.state == "active" for i in episodes) == 1
    # Identical context within five minutes must not coalesce across episodes.
    logs = [r for r in await read_all(NotificationLog) if r.incident_event == "firing"]
    assert len(logs) == 2
    assert len({r.incident_id for r in logs}) == 2


async def test_recovery_expression_error_is_unknown_not_healthy(scenario):
    engine, rule_id = scenario
    await open_problem(scenario)
    async with get_session_factory()() as session:
        rule = await session.get(Rule, rule_id)
        rule.recovery_expr = "x < 75 and y > 0"
        await session.commit()
    await engine.reload_rules()
    assert engine._rules[rule_id].rule.recovery_expr == "x < 75 and y > 0"
    await evaluate(engine, rule_id, 70)
    [incident] = await read_all(Incident)
    assert incident.state == "active"
    assert engine._rules[rule_id].recovery_match_count == 0
    assert engine._rules[rule_id].consecutive_eval_errors == 1
    [rule] = await read_all(Rule)
    assert "y" in rule.last_eval_error


async def test_recovery_condition_is_only_evaluated_for_an_open_problem(scenario):
    engine, rule_id = scenario
    async with get_session_factory()() as session:
        rule = await session.get(Rule, rule_id)
        rule.recovery_expr = "x < 75 and y > 0"
        await session.commit()
    await engine.reload_rules()
    await evaluate(engine, rule_id, 70)
    assert await read_all(Incident) == []
    [rule] = await read_all(Rule)
    assert rule.last_eval_error is None
    assert rule.consecutive_eval_errors == 0


async def test_default_recovery_can_resolve_without_a_notice(scenario):
    engine, rule_id = scenario
    async with get_session_factory()() as session:
        rule = await session.get(Rule, rule_id)
        rule.recovery_expr = None
        rule.resolved_template_type = None
        await session.commit()
    await engine.reload_rules()
    await open_problem((engine, rule_id))
    await evaluate(engine, rule_id, 78)
    await evaluate(engine, rule_id, 78)
    assert (await read_all(Incident))[0].state == "resolved"
    assert len(await read_all(NotificationLog)) == 1


async def test_open_and_notification_rollback_together(scenario):
    engine, rule_id = scenario
    with patch("app.core.dispatcher.fire", side_effect=RuntimeError("before durable commit")):
        async with get_session_factory()() as session:
            with pytest.raises(RuntimeError):
                await incidents.fire_rule(session, engine._rules[rule_id].rule, 0, {"x": 90})
    assert await read_all(Incident) == []
    assert await read_all(NotificationLog) == []
    assert await read_all(Delivery) == []


async def test_resolution_and_recovery_notice_roll_back_together(scenario):
    engine, rule_id = scenario
    original = await open_problem(scenario)
    with patch("app.core.dispatcher.fire", side_effect=RuntimeError("before recovery commit")):
        async with get_session_factory()() as session:
            with pytest.raises(RuntimeError):
                await incidents.recover_rule(session, engine._rules[rule_id].rule, 0, {"x": 70})
    [incident] = await read_all(Incident)
    assert incident.id == original.id
    assert incident.state == "active"
    [delivery] = await read_all(Delivery)
    assert delivery.state == DeliveryState.pending
    assert len(await read_all(NotificationLog)) == 1


async def test_config_roundtrip_dry_run_and_apply_preserve_lifecycle_transaction(scenario):
    from app.services.config_io import export_config, import_config

    await open_problem(scenario)
    async with get_session_factory()() as session:
        pack = await export_config(session)
        fields = pack["rules"][0]
        assert fields["incident_enabled"] is True
        assert fields["recovery_expr"] == "x < 75"
        assert fields["recovery_persist_n"] == 2
        assert fields["resolved_template_type"] == "temperature_normal"
        fields["recovery_expr"] = "x < 60"
        plan = await import_config(session, pack, apply=False)
        assert not plan.errors, plan.errors
    assert (await read_all(Incident))[0].state == "active"
    async with get_session_factory()() as session:
        plan = await import_config(session, pack, apply=True)
        assert not plan.errors, plan.errors
        await session.commit()
    [incident] = await read_all(Incident)
    assert incident.resolution_reason == "rule_reconfigured"
    assert len(await read_all(NotificationLog)) == 1


async def test_recovery_delivery_does_not_increment_rule_alarm_counter(scenario):
    engine, rule_id = scenario
    await open_problem(scenario)

    async def drain():
        async with get_session_factory()() as session:
            for delivery in (await session.execute(select(Delivery).where(Delivery.state == DeliveryState.pending))).scalars():
                delivery.next_attempt_at = utc_now() - timedelta(seconds=2)
                delivery.lease_until = None
            await session.commit()
        with patch("app.channels.manager.ChannelManager.dispatch", return_value=DispatchOutcome(succeeded=["incident_ui"])):
            await DeliveryWorker().tick()

    await drain()
    assert (await read_all(Rule))[0].fire_count_lifetime == 1
    await evaluate(engine, rule_id, 70)
    await evaluate(engine, rule_id, 70)
    await drain()
    assert (await read_all(Rule))[0].fire_count_lifetime == 1
    assert all(row.delivery_status == DeliveryStatus.sent for row in await read_all(NotificationLog))


async def test_retention_keeps_active_episodes_and_pending_notices(db_session):
    from app.core.retention import RetentionService

    old = utc_now() - timedelta(days=120)
    for ident, resolved in (("active", False), ("old", True), ("referenced", True), ("pending", True)):
        db_session.add(Incident(
            id=ident, rule_name="retired", template_type="alarm", severity=Severity.warning,
            title=ident, opened_at=old, resolved_at=old if resolved else None, opening_context={},
        ))
    await db_session.flush()
    for ident, stamp in (("referenced", utc_now()), ("pending", old)):
        db_session.add(NotificationLog(
            id=ident, incident_id=ident, incident_event="resolved", type="normal",
            severity=Severity.info, title=ident, fired_at=stamp,
        ))
    await db_session.flush()
    d = outbox.enqueue(db_session, "pending", ["ui"], background_only=True)[0]
    await db_session.commit()
    await RetentionService()._sweep()
    assert {i.id for i in await read_all(Incident)} == {"active", "referenced", "pending"}
    d.state = DeliveryState.failed
    d.next_attempt_at = None
    await db_session.commit()
    await RetentionService()._sweep()
    assert {i.id for i in await read_all(Incident)} == {"active", "referenced"}


async def test_ack_stays_active_and_covers_future_repeat_notifications(scenario):
    engine, rule_id = scenario
    original = await open_problem(scenario)
    async with get_session_factory()() as session:
        incident = await session.get(Incident, original.id)
        await incidents.acknowledge(session, incident, "operator")
        await session.commit()
    await evaluate(engine, rule_id, 95)
    await evaluate(engine, rule_id, 95)
    [incident] = await read_all(Incident)
    assert incident.state == "active"
    assert incident.acknowledged_by == "operator"
    logs = await read_all(NotificationLog)
    assert len(logs) == 2
    assert all(r.acknowledged_by == "operator" for r in logs)
    async with get_session_factory()() as session:
        for row in (await session.execute(select(NotificationLog))).scalars():
            row.fired_at = utc_now() - timedelta(minutes=30)
            row.acknowledged_at = None  # parent remains the authoritative ack
        await session.commit()
    assert await EscalationService().sweep_once() == 0


async def test_worker_checks_resolution_after_an_expired_lease(scenario):
    engine, rule_id = scenario
    await open_problem(scenario)
    async with get_session_factory()() as session:
        d = (await session.execute(select(Delivery))).scalar_one()
        d.lease_until = utc_now() + timedelta(minutes=1)
        await session.commit()
    await evaluate(engine, rule_id, 70)
    await evaluate(engine, rule_id, 70)
    async with get_session_factory()() as session:
        d = (await session.execute(select(Delivery).where(Delivery.notification_id.in_(
            select(NotificationLog.id).where(NotificationLog.incident_event == "firing")
        )))).scalar_one()
        assert d.state == DeliveryState.pending
        d.lease_until = utc_now() - timedelta(seconds=2)
        d.next_attempt_at = utc_now() - timedelta(seconds=2)
        # Leave the recovery notice scheduled later so this only checks cancellation.
        for other in (await session.execute(select(Delivery).where(Delivery.id != d.id))).scalars():
            other.next_attempt_at = utc_now() + timedelta(minutes=1)
        await session.commit()
    with patch("app.channels.manager.ChannelManager.dispatch", new_callable=AsyncMock) as send:
        assert await DeliveryWorker().tick() == 1
        send.assert_not_awaited()
    [log] = [r for r in await read_all(NotificationLog) if r.incident_event == "firing"]
    assert log.delivery_status == DeliveryStatus.cancelled


@pytest.mark.mysql
async def test_concurrent_fires_open_one_episode_and_one_notice(scenario):
    engine, rule_id = scenario

    async def fire():
        async with get_session_factory()() as session:
            await incidents.fire_rule(session, engine._rules[rule_id].rule, 0, {"x": 90})
            await session.commit()

    await asyncio.gather(fire(), fire())
    assert len(await read_all(Incident)) == 1
    assert len(await read_all(NotificationLog)) == 1
    assert len(await read_all(Delivery)) == 1


@pytest.mark.mysql
async def test_resolution_racing_an_inflight_delivery_has_no_lock_inversion(scenario):
    engine, rule_id = scenario
    await open_problem(scenario)
    async with get_session_factory()() as session:
        d = (await session.execute(select(Delivery))).scalar_one()
        d.next_attempt_at = utc_now() - timedelta(seconds=2)
        await session.commit()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_send(*args, **kwargs):
        started.set()
        await release.wait()
        return DispatchOutcome(succeeded=["incident_ui"])

    async def recover():
        async with get_session_factory()() as session:
            changed = await incidents.recover_rule(session, engine._rules[rule_id].rule, 0, {"x": 70})
            await session.commit()
            return changed

    with patch("app.channels.manager.ChannelManager.dispatch", side_effect=slow_send):
        worker = asyncio.create_task(DeliveryWorker().tick())
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            recovery = asyncio.create_task(recover())
            await asyncio.sleep(0.05)
            release.set()
            results = await asyncio.wait_for(asyncio.gather(worker, recovery), timeout=10)
            assert results == [1, True]
        finally:
            release.set()
            if not worker.done():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
    assert (await read_all(Incident))[0].state == "resolved"
    firing = [r for r in await read_all(NotificationLog) if r.incident_event == "firing"][0]
    assert firing.delivery_status == DeliveryStatus.sent
