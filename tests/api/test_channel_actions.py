"""F3: POST /v1/channels/{id}/breaker/reset."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def test_breaker_reset(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={"name": "wh1", "kind": "webhook",
                                                   "config": {"url": "http://x"}}, headers=h)
    cid = r.json()["id"]

    # Trip the breaker directly, then reset via the endpoint.
    from app.channels.manager import get_channel_manager
    mgr = get_channel_manager()
    for _ in range(10):
        await mgr._breaker.record_failure("wh1", "boom")
    assert mgr._breaker.health("wh1")["state"] == "open"

    r = await db_client.post(f"/v1/channels/{cid}/breaker/reset", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "closed"
    assert mgr._breaker.health("wh1")["state"] == "closed"


async def test_breaker_reset_requires_admin(db_client, admin_key, db_session):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={"name": "wh2", "kind": "ui"}, headers=h)
    cid = r.json()["id"]

    import bcrypt

    from app.db.models import ApiKey
    pt = "alertd_ack_key_wwwwwwwwwwwww"
    db_session.add(ApiKey(id=88, name="acker",
                          key_hash=bcrypt.hashpw(pt.encode(), bcrypt.gensalt(rounds=4)).decode(),
                          key_prefix=pt[:8], scopes=["read", "ack"], enabled=True))
    await db_session.commit()
    r = await db_client.post(f"/v1/channels/{cid}/breaker/reset", headers={"X-API-Key": pt})
    assert r.status_code == 403


async def test_breaker_reset_unknown_channel_404(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels/999999/breaker/reset", headers=h)
    assert r.status_code == 404
