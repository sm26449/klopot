"""Delivery detail is read-only, excludes credentials, and ack stops queued escalation."""
from __future__ import annotations

from datetime import timedelta

import bcrypt
import pytest

from app.core import outbox
from app.db.models import ApiKey, DeliveryState, DeliveryStatus, NotificationLog, Severity
from app.utils.time import utc_now


async def _seed(session):
    row = NotificationLog(
        id="delivery_detail", type="critical_alarm", severity=Severity.critical,
        title="Alarm", delivery_status=DeliveryStatus.sent, dispatched_to=["sms_main"],
    )
    session.add(row)
    await session.flush()
    initial = outbox.enqueue(
        session, row.id, ["sms_main"],
        effective_by_name={"sms_main": {"password": "private-destination-secret"}},
    )[0]
    outbox.apply_attempt(initial, ok=True)
    escalation = outbox.enqueue(session, row.id, ["sms_main"], purpose="escalation")[0]
    outbox.apply_attempt(
        escalation, ok=False,
        error="POST https://user:private-pass@host/botprivate-token/send?token=private-key 503",
    )
    await session.commit()
    return row, initial, escalation


async def test_delivery_detail_does_not_expose_frozen_secrets(db_client, db_session, admin_key):
    row, _, _ = await _seed(db_session)
    r = await db_client.get(f"/v1/log/{row.id}", headers={"X-API-Key": admin_key})
    assert r.status_code == 200, r.text
    body = r.json()
    ds = body["deliveries"]
    assert len(ds) == 2
    by_purpose = {d["purpose"]: d for d in ds}
    assert by_purpose["notification"]["state"] == "sent"
    esc = by_purpose["escalation"]
    assert esc["channel"] == "sms_main"
    assert esc["state"] == "pending"
    assert esc["attempts"] == 1
    assert esc["max_attempts"] == outbox.MAX_ATTEMPTS
    assert esc["next_attempt_at"].endswith("Z")
    assert esc["updated_at"].endswith("Z")
    assert esc["created_at"].endswith("Z")
    assert "private-" not in r.text
    assert "effective_config" not in r.text
    assert "channel_overrides" not in r.text
    assert "idempotency_key" not in r.text
    assert body["delivery_status"] == "sent"
    # The list keeps its existing lightweight response shape.
    listing = await db_client.get("/v1/log", headers={"X-API-Key": admin_key})
    assert "deliveries" not in listing.json()["items"][0]


async def test_old_notification_has_empty_delivery_details(db_client, db_session, admin_key):
    db_session.add(NotificationLog(
        id="legacy", type="legacy", severity=Severity.info, title="Old",
    ))
    await db_session.commit()
    r = await db_client.get("/v1/log/legacy", headers={"X-API-Key": admin_key})
    assert r.status_code == 200
    assert r.json()["deliveries"] == []


@pytest.mark.parametrize("leased", [False, True])
async def test_ack_cancels_only_queued_escalation(
    db_client, db_session, admin_key, leased,
):
    row, initial, escalation = await _seed(db_session)
    if leased:
        escalation.lease_until = utc_now() + timedelta(seconds=60)
        await db_session.commit()
    r = await db_client.post(f"/v1/log/{row.id}/ack", headers={"X-API-Key": admin_key})
    assert r.status_code == 200, r.text
    await db_session.refresh(initial)
    await db_session.refresh(escalation)
    await db_session.refresh(row)
    assert row.acknowledged_at is not None
    assert row.delivery_status == DeliveryStatus.sent
    assert initial.state == DeliveryState.sent
    assert escalation.attempts == 1
    assert escalation.state == (DeliveryState.pending if leased else DeliveryState.cancelled)
    if not leased:
        assert escalation.next_attempt_at is None
        assert escalation.last_error is None


async def test_read_scope_can_inspect_but_cannot_ack(db_client, db_session):
    key = "delivery_read_key_12345678"
    db_session.add(ApiKey(
        name="delivery_reader", key_prefix=key[:8],
        key_hash=bcrypt.hashpw(key.encode(), bcrypt.gensalt(rounds=4)).decode(),
        scopes=["read"], enabled=True,
    ))
    row, _, _ = await _seed(db_session)
    assert (await db_client.get(f"/v1/log/{row.id}", headers={"X-API-Key": key})).status_code == 200
    assert (await db_client.post(f"/v1/log/{row.id}/ack", headers={"X-API-Key": key})).status_code == 403
    assert (await db_client.get(f"/v1/log/{row.id}")).status_code == 401
