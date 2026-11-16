"""F3 (M-2): POST /v1/api_keys/{id}/rotate?grace_sec=."""
from __future__ import annotations

from app.db.models import ApiKey


async def _mk_key(db_client, h, name="svc"):
    r = await db_client.post("/v1/api_keys", json={"name": name, "scopes": ["fire"]}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def test_rotate_no_grace_disables_old(db_client, admin_key, db_session):
    h = {"X-API-Key": admin_key}
    key = await _mk_key(db_client, h)
    r = await db_client.post(f"/v1/api_keys/{key['id']}/rotate", headers=h)
    assert r.status_code == 200, r.text
    assert "key" in r.json()
    old = await db_session.get(ApiKey, key["id"])
    await db_session.refresh(old)
    assert old.enabled is False
    assert old.expires_at is None


async def test_rotate_with_grace_keeps_old_until_expiry(db_client, admin_key, db_session):
    h = {"X-API-Key": admin_key}
    key = await _mk_key(db_client, h, "svc2")
    r = await db_client.post(f"/v1/api_keys/{key['id']}/rotate", params={"grace_sec": 300}, headers=h)
    assert r.status_code == 200
    old = await db_session.get(ApiKey, key["id"])
    await db_session.refresh(old)
    assert old.enabled is True          # still valid during grace
    assert old.expires_at is not None   # but expiring soon


async def test_rotate_grace_out_of_range_422(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    key = await _mk_key(db_client, h, "svc3")
    r = await db_client.post(f"/v1/api_keys/{key['id']}/rotate", params={"grace_sec": 9999}, headers=h)
    assert r.status_code == 422
