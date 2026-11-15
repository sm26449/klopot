"""Generic provider lifecycle (app/core/provider_lifecycle.py): Pushover
emergency receipts cancelled on acknowledgement, and acknowledgements made in
the Pushover app applied in Klopot — each exactly once."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import provider_lifecycle as pl
from app.core.notification_actions import acknowledge_notification
from app.db.models import (
    Delivery,
    DeliveryState,
    DeliveryStatus,
    InboundEvent,
    LifecycleCommand,
    NotificationLog,
    Severity,
)
from app.utils.time import utc_now
from tests._db import fresh_rows

CONFIG = {"user_key": "u_key_1234", "app_token": "a_tok_1234"}


@pytest.fixture
async def emergency(db_session):
    """A sent notification with one Pushover emergency delivery (receipt R1)."""
    now = utc_now()
    db_session.add(NotificationLog(
        id="ntf_em", type="disk_full", severity=Severity.critical, title="Disk full",
        delivery_status=DeliveryStatus.sent, is_test=False, fired_at=now,
    ))
    await db_session.flush()
    db_session.add(Delivery(
        notification_id="ntf_em", channel="pager", purpose="notification", state=DeliveryState.sent,
        attempts=1, idempotency_key="k", effective_config=CONFIG, effective_kind="pushover",
        provider_ref="pushover:receipt:R1",
    ))
    await db_session.commit()


async def _fresh(db_session, query):
    return await fresh_rows(db_session, query)


async def test_ack_in_klopot_queues_one_cancellation(db_session, emergency):
    assert await acknowledge_notification(db_session, "ntf_em", "admin")
    assert await acknowledge_notification(db_session, "ntf_em", "admin")   # second ack
    await db_session.commit()
    [cmd] = await _fresh(db_session, select(LifecycleCommand))
    assert (cmd.provider, cmd.action, cmd.ref, cmd.state) == ("pushover", "cancel_receipt", "R1", "pending")


async def test_commands_run_with_backoff_then_succeed(db_session, emergency, monkeypatch):
    await acknowledge_notification(db_session, "ntf_em", "admin")
    await db_session.commit()
    outcomes = ["HTTP 503: busy", None]
    seen = []

    async def cancel(config, receipt):
        seen.append((config["app_token"], receipt))
        return outcomes.pop(0)

    monkeypatch.setattr(pl.pushover, "cancel_receipt", cancel)
    assert await pl.run_due_commands(db_session) == 1
    await db_session.commit()
    [cmd] = await _fresh(db_session, select(LifecycleCommand))
    assert cmd.state == "pending" and cmd.attempts == 1 and cmd.last_error == "HTTP 503: busy"
    assert cmd.next_attempt_at > utc_now(), "backed off"

    assert await pl.run_due_commands(db_session) == 0, "not due yet"
    cmd.next_attempt_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    await pl.run_due_commands(db_session)
    await db_session.commit()
    [cmd] = await _fresh(db_session, select(LifecycleCommand))
    assert cmd.state == "done" and cmd.last_error is None
    assert seen == [("a_tok_1234", "R1"), ("a_tok_1234", "R1")], "uses the config the message was sent with"


async def test_command_gives_up_after_max_attempts(db_session, emergency, monkeypatch):
    await acknowledge_notification(db_session, "ntf_em", "admin")
    await db_session.commit()

    async def cancel(config, receipt):
        return "HTTP 500"

    monkeypatch.setattr(pl.pushover, "cancel_receipt", cancel)
    for _ in range(pl.MAX_ATTEMPTS):
        for cmd in await _fresh(db_session, select(LifecycleCommand)):
            cmd.next_attempt_at = None
        await db_session.commit()
        await pl.run_due_commands(db_session)
        await db_session.commit()
    [cmd] = await _fresh(db_session, select(LifecycleCommand))
    assert cmd.state == "failed" and cmd.attempts == pl.MAX_ATTEMPTS


async def test_ack_in_the_pushover_app_is_applied_once(db_session, emergency, monkeypatch):
    calls = []

    async def status(config, receipt):
        calls.append(receipt)
        return {"status": 1, "acknowledged": 1, "acknowledged_by_device": "pixel"}

    monkeypatch.setattr(pl.pushover, "receipt_status", status)
    assert await pl.poll_receipts(db_session) == 1
    await db_session.commit()
    [log] = await _fresh(db_session, select(NotificationLog))
    assert log.acknowledged_by == "pushover:pixel"
    [event] = await _fresh(db_session, select(InboundEvent))
    assert (event.provider, event.event_key, event.result) == ("pushover", "receipt:R1", "acknowledged")

    assert await pl.poll_receipts(db_session) == 0
    assert calls == ["R1"], "an acknowledged notification is not polled again"


async def test_expired_receipt_is_recorded_and_no_longer_polled(db_session, emergency, monkeypatch):
    calls = []

    async def status(config, receipt):
        calls.append(receipt)
        return {"status": 1, "acknowledged": 0, "expired": 1}

    monkeypatch.setattr(pl.pushover, "receipt_status", status)
    assert await pl.poll_receipts(db_session) == 0
    await db_session.commit()
    assert await pl.poll_receipts(db_session) == 0
    assert calls == ["R1"]
    [log] = await _fresh(db_session, select(NotificationLog))
    assert log.acknowledged_at is None


async def test_unreadable_receipt_is_retried_next_poll(db_session, emergency, monkeypatch):
    calls = []

    async def status(config, receipt):
        calls.append(receipt)
        return None

    monkeypatch.setattr(pl.pushover, "receipt_status", status)
    await pl.poll_receipts(db_session)
    await pl.poll_receipts(db_session)
    assert calls == ["R1", "R1"]


async def test_incident_ack_cancels_receipts_of_all_its_notifications(db_session, emergency):
    from app.core import incidents
    from app.db.models import Incident

    inc = Incident(id="inc_em", rule_id=None, rule_name="disk", template_type="disk_full",
                   severity=Severity.critical, title="Disk full", opened_at=utc_now().replace(microsecond=0),
                   opening_context={}, source_kind="fire", source_key="fire:x:k", active_source_key="fire:x:k")
    db_session.add(inc)
    log = await db_session.get(NotificationLog, "ntf_em")
    log.incident_id, log.incident_event = "inc_em", "firing"
    await db_session.commit()
    await incidents.acknowledge(db_session, inc, "admin")
    await db_session.commit()
    [cmd] = await _fresh(db_session, select(LifecycleCommand))
    assert cmd.ref == "R1"
