"""A snooze reason is bounded (second review): the column is TEXT, 64 KiB on
MySQL, and a longer reason from an ``ack`` key was a 500 instead of a 422."""
from __future__ import annotations

from datetime import timedelta

from app.utils.time import utc_now


async def test_an_over_long_reason_is_refused(db_client, admin_key):
    until = (utc_now() + timedelta(hours=1)).isoformat() + "Z"
    body = {"scope": "type", "target": "disk_full", "until": until, "reason": "x" * 501}
    r = await db_client.post("/v1/snooze", headers={"X-API-Key": admin_key}, json=body)
    assert r.status_code == 422
    ok = await db_client.post("/v1/snooze", headers={"X-API-Key": admin_key}, json={**body, "reason": "maintenance"})
    assert ok.status_code in (200, 201), ok.text[:200]
