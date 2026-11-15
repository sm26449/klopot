"""Who paused a push device is recorded, not guessed (review K11).

5603369 inferred "the service paused it" from ``enabled = false AND
consecutive_failures >= 20``. That broke both ways:

- re-registering an auto-paused device (the user taps "Enable on this device")
  reset its streak but left it disabled — no longer "auto-paused", so alerts
  went back to "sent to 0 devices";
- a device the operator kept paused after the service paused it (renamed,
  filtered) made every push-only alert fail, for good.

And when every device refuses us with 401/403 the fault is our VAPID
identity, not the devices: that must not pause them all.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.channels import push
from app.channels.push import PushChannel
from app.db.models import PushSubscription
from tests._db import fresh
from tests.api.test_push_api import _sub, browser  # noqa: F401  (fixture)
from tests.channels.test_push import CONFIG, Device, _notif, _resp

pytestmark = pytest.mark.anyio


async def _only(db_session) -> PushSubscription:
    await fresh(db_session)
    return (await db_session.execute(select(PushSubscription))).scalar_one()


async def test_the_service_records_that_it_paused_a_device(db_engine, db_session):
    db_session.add(Device().row(consecutive_failures=push.DISABLE_AFTER_FAILURES - 1))
    await db_session.commit()
    with patch("app.channels.push.safe_request", AsyncMock(return_value=_resp(500))):
        await PushChannel().send(_notif(), CONFIG)
    row = await _only(db_session)
    assert row.enabled is False
    assert row.paused_reason == "service"


async def test_a_device_kept_paused_by_the_operator_is_not_a_failure(db_engine, db_session):
    db_session.add(Device().row(enabled=False, consecutive_failures=push.DISABLE_AFTER_FAILURES,
                                paused_reason="operator"))
    await db_session.commit()
    r = await PushChannel().send(_notif(severity="critical"), CONFIG)
    assert r.ok is True
    assert r.response == {"devices": 0, "delivered": 0}


async def test_a_failure_racing_an_operator_pause_does_not_count(db_engine, db_session):
    """Copilot C19: the operator pauses a device while a send to it is in flight."""
    db_session.add(Device().row(consecutive_failures=push.DISABLE_AFTER_FAILURES - 1))
    await db_session.commit()
    row = await _only(db_session)
    outcome = push.DeviceOutcome(row.id, False, status=500, error="HTTP 500")
    row.enabled, row.paused_reason = False, "operator"
    await db_session.commit()
    await push.record_outcomes([outcome], {row.id: row.label})
    row = await _only(db_session)
    assert row.paused_reason == "operator"
    assert row.consecutive_failures == push.DISABLE_AFTER_FAILURES - 1


async def test_every_device_refusing_our_identity_pauses_none(db_engine, db_session):
    db_session.add_all([Device("https://web.push.apple.com/a").row(consecutive_failures=push.DISABLE_AFTER_FAILURES - 1),
                        Device("https://fcm.googleapis.com/fcm/send/b").row(consecutive_failures=push.DISABLE_AFTER_FAILURES - 1)])
    await db_session.commit()
    with patch("app.channels.push.safe_request", AsyncMock(return_value=_resp(403, text="BadJwtToken"))):
        r = await PushChannel().send(_notif(), CONFIG)
    assert r.ok is False
    assert "VAPID" in r.error
    await fresh(db_session)
    rows = (await db_session.execute(select(PushSubscription))).scalars().all()
    assert [d.enabled for d in rows] == [True, True]
    assert [d.consecutive_failures for d in rows] == [push.DISABLE_AFTER_FAILURES - 1] * 2


async def test_one_device_refusing_still_counts_for_that_device(db_engine, db_session):
    db_session.add_all([Device("https://web.push.apple.com/a").row(),
                        Device("https://fcm.googleapis.com/fcm/send/b").row()])
    await db_session.commit()

    async def answer(method, url, **kw):
        return _resp(201) if "apple" in url else _resp(403)

    with patch("app.channels.push.safe_request", AsyncMock(side_effect=answer)):
        assert (await PushChannel().send(_notif(), CONFIG)).ok is True
    await fresh(db_session)
    bad = (await db_session.execute(select(PushSubscription).where(
        PushSubscription.endpoint.like("%fcm%")))).scalar_one()
    assert bad.consecutive_failures == 1


async def test_registering_again_re_enables_an_auto_paused_device(browser, db_session):  # noqa: F811
    client, h = browser
    dev = Device()
    created = (await client.post("/v1/push/subscriptions", headers=h, json=_sub(dev))).json()
    row = await _only(db_session)
    row.enabled, row.paused_reason, row.consecutive_failures = False, "service", push.DISABLE_AFTER_FAILURES
    await db_session.commit()
    again = await client.post("/v1/push/subscriptions", headers=h, json=_sub(dev))
    assert again.status_code == 200
    assert again.json()["id"] == created["id"]
    assert again.json()["enabled"] is True
    assert again.json()["paused_reason"] is None


async def test_the_operator_pausing_and_resuming_is_recorded(browser, db_session):  # noqa: F811
    client, h = browser
    created = (await client.post("/v1/push/subscriptions", headers=h, json=_sub(Device()))).json()
    paused = await client.patch(f"/v1/push/subscriptions/{created['id']}", headers=h, json={"enabled": False})
    assert paused.json()["paused_reason"] == "operator"
    resumed = await client.patch(f"/v1/push/subscriptions/{created['id']}", headers=h, json={"enabled": True})
    assert resumed.json()["paused_reason"] is None
    assert resumed.json()["enabled"] is True
