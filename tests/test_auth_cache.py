"""API-key resolve cache: revocation must be immediate (audit 2026-11-07 H-4).

Before ``invalidate_key_cache`` a disabled / deleted / rotated key kept
working for up to ``_KEY_CACHE_TTL_SEC`` (30 s).
"""
from __future__ import annotations

import pytest

from app import auth
from app.auth import Actor, invalidate_key_cache


@pytest.fixture(autouse=True)
def _clean_cache():
    invalidate_key_cache()
    yield
    invalidate_key_cache()


def _actor(key_id: int) -> Actor:
    return Actor(kind="api_key", id=key_id, name=f"k{key_id}", scopes=frozenset({"read"}))


def test_invalidate_one_key_leaves_others():
    auth._key_cache_set("alertd_raw_key_one_xxxxxxxx", _actor(1))
    auth._key_cache_set("alertd_raw_key_two_xxxxxxxx", _actor(2))
    assert invalidate_key_cache(1) == 1
    assert auth._key_cache_get("alertd_raw_key_one_xxxxxxxx") is None
    assert auth._key_cache_get("alertd_raw_key_two_xxxxxxxx") is not None


def test_invalidate_all():
    auth._key_cache_set("alertd_raw_key_one_xxxxxxxx", _actor(1))
    auth._key_cache_set("alertd_raw_key_two_xxxxxxxx", _actor(2))
    assert invalidate_key_cache() == 2
    assert auth._key_cache_get("alertd_raw_key_one_xxxxxxxx") is None


def test_invalidate_unknown_is_noop():
    auth._key_cache_set("alertd_raw_key_one_xxxxxxxx", _actor(1))
    assert invalidate_key_cache(99) == 0
    assert auth._key_cache_get("alertd_raw_key_one_xxxxxxxx") is not None


# ── A33: cached key honours its own expiry on every hit ──────────


def test_expired_key_not_served_from_cache():
    from datetime import timedelta

    from app.utils.time import utc_now

    raw = "alertd_raw_key_exp_xxxxxxxx"
    auth._key_cache_set(raw, _actor(7), utc_now() - timedelta(seconds=1))
    # TTL hasn't lapsed, but the key is past expires_at — must miss.
    assert auth._key_cache_get(raw) is None


def test_unexpired_key_served_from_cache():
    from datetime import timedelta

    from app.utils.time import utc_now

    raw = "alertd_raw_key_future_xxxxxxxx"
    auth._key_cache_set(raw, _actor(8), utc_now() + timedelta(hours=1))
    assert auth._key_cache_get(raw) is not None


def test_key_without_expiry_served_from_cache():
    raw = "alertd_raw_key_noexp_xxxxxxxx"
    auth._key_cache_set(raw, _actor(9), None)
    assert auth._key_cache_get(raw) is not None


async def test_cached_key_rejected_once_expiry_passes(db_client, admin_key):
    """End-to-end A33: a key cached while valid must be rejected as soon
    as its expiry passes — without any disable/revoke, purely by time —
    i.e. the cache hit itself enforces expiry, not just the DB read."""
    from datetime import timedelta
    from unittest.mock import patch

    from app.utils.time import utc_now

    h = {"X-API-Key": admin_key}
    expires = (utc_now() + timedelta(minutes=5)).isoformat()
    r = await db_client.post(
        "/v1/api_keys",
        json={"name": "ttl_victim", "scopes": ["read"], "expires_at": expires},
        headers=h,
    )
    assert r.status_code == 201, r.text
    victim_key = r.json()["key"]
    vh = {"X-API-Key": victim_key}

    # First request resolves + caches the key (with its future expiry).
    assert (await db_client.get("/v1/templates", headers=vh)).status_code == 200

    # Advance time past the expiry. No invalidation is called — the cache
    # entry is still within its 30 s TTL, so only the per-hit expiry check
    # can reject it.
    later = utc_now() + timedelta(minutes=10)
    with patch("app.auth.utc_now", return_value=later):
        assert (await db_client.get("/v1/templates", headers=vh)).status_code == 401


# ── end-to-end: disable → immediate 401 ──────────────────────────


async def test_disabled_key_rejected_on_next_request(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/api_keys", json={"name": "victim", "scopes": ["read"]}, headers=h)
    assert r.status_code == 201, r.text
    victim_id, victim_key = r.json()["id"], r.json()["key"]

    vh = {"X-API-Key": victim_key}
    assert (await db_client.get("/v1/templates", headers=vh)).status_code == 200  # now cached

    r = await db_client.patch(f"/v1/api_keys/{victim_id}", json={"enabled": False}, headers=h)
    assert r.status_code == 200
    assert (await db_client.get("/v1/templates", headers=vh)).status_code == 401


async def test_deleted_key_rejected_on_next_request(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/api_keys", json={"name": "victim2", "scopes": ["read"]}, headers=h)
    victim_id, victim_key = r.json()["id"], r.json()["key"]
    vh = {"X-API-Key": victim_key}
    assert (await db_client.get("/v1/templates", headers=vh)).status_code == 200

    assert (await db_client.delete(f"/v1/api_keys/{victim_id}", headers=h)).status_code == 204
    assert (await db_client.get("/v1/templates", headers=vh)).status_code == 401


async def test_rotated_old_key_rejected_on_next_request(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/api_keys", json={"name": "victim3", "scopes": ["read"]}, headers=h)
    victim_id, old_key = r.json()["id"], r.json()["key"]
    oh = {"X-API-Key": old_key}
    assert (await db_client.get("/v1/templates", headers=oh)).status_code == 200

    r = await db_client.post(f"/v1/api_keys/{victim_id}/rotate", headers=h)
    assert r.status_code == 200, r.text
    new_key = r.json()["key"]
    assert (await db_client.get("/v1/templates", headers=oh)).status_code == 401
    assert (await db_client.get("/v1/templates", headers={"X-API-Key": new_key})).status_code == 200


async def test_hash_key_async_roundtrips_with_bcrypt():
    import bcrypt

    from app.auth import hash_key_async

    raw = "alertd_" + "x" * 36
    h = await hash_key_async(raw)
    assert bcrypt.checkpw(raw.encode(), h.encode())
