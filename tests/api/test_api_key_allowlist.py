"""Per-key source allowlist (`api_keys.allowed_cidrs`, migration 0042).

A key may be limited to IPs / CIDRs (IPv4 and IPv6). A request with it from
anywhere else gets 403 — after the key is known to be right, before its use
is recorded — and counts once as a wrong key for that address, on every
resolution path: cache hit, digest (generated keys) and bcrypt (operator-chosen
keys). Empty = any address, which every existing key keeps.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth
from app.db.models import ApiKey
from app.schemas.api_key import normalize_allowed_cidrs

OFFICE = "203.0.113.0/24"
INSIDE, OUTSIDE = "203.0.113.7", "198.51.100.9"


def _failures(ip: str) -> int:
    return auth._KEY_BUDGET.count(ip)


async def _resolve(raw: str, ip: str | None):
    from app.db import session as session_module

    async with session_module._session_factory() as s:
        actor = await auth._resolve_key(raw, s, ip)
        await s.commit()
        return actor


async def _key(db_client, admin_key, **body) -> dict:
    r = await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key},
                             json={"name": "script", "scopes": ["fire"], **body})
    assert r.status_code == 201, r.text
    return r.json()


# ── Validation ────────────────────────────────────────────────────────


def test_entries_are_normalised_deduplicated_and_ordered():
    assert normalize_allowed_cidrs(["203.0.113.7/24", " 198.51.100.9", "2001:db8::1/64", "203.0.113.0/24"]) == [
        "203.0.113.0/24", "198.51.100.9/32", "2001:db8::/64"]


@pytest.mark.parametrize(("entries", "message"), [
    (["0.0.0.0/0"], "leave the list empty"), (["::/0"], "leave the list empty"),
    (["not-an-ip"], "not an IP address or CIDR"), (["10.0.0.1"] * 65, "at most 64"),
])
def test_invalid_lists_are_refused(entries, message):
    with pytest.raises(ValueError, match=message):
        normalize_allowed_cidrs(entries)


async def test_the_api_stores_and_returns_the_normalised_list(db_client, admin_key):
    created = await _key(db_client, admin_key, allowed_cidrs=["203.0.113.7/24"])
    got = (await db_client.get(f"/v1/api_keys/{created['id']}", headers={"X-API-Key": admin_key})).json()
    assert got["allowed_cidrs"] == [OFFICE]
    bad = await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key},
                               json={"name": "open", "scopes": ["fire"], "allowed_cidrs": ["0.0.0.0/0"]})
    assert bad.status_code == 422


# ── Enforcement ───────────────────────────────────────────────────────


async def test_a_generated_key_works_inside_and_is_refused_outside_counted_once(db_client, admin_key):
    raw = (await _key(db_client, admin_key, allowed_cidrs=[OFFICE]))["key"]
    assert (await _resolve(raw, INSIDE)).name == "script"
    auth.invalidate_key_cache()
    with pytest.raises(HTTPException) as refused:
        await _resolve(raw, OUTSIDE)
    assert refused.value.status_code == 403
    assert _failures(OUTSIDE) == 1
    assert _failures(INSIDE) == 0


async def test_a_cache_hit_is_checked_against_its_own_address(db_client, admin_key):
    raw = (await _key(db_client, admin_key, allowed_cidrs=[OFFICE]))["key"]
    await _resolve(raw, INSIDE)                          # fills the cache
    with pytest.raises(HTTPException) as refused:
        await _resolve(raw, OUTSIDE)                     # same key, cached, other address
    assert refused.value.status_code == 403
    assert _failures(OUTSIDE) == 1


async def test_an_operator_chosen_key_on_the_bcrypt_path_is_counted_once(db_session):
    raw = "operator-chosen-key-for-the-ups-0001"
    db_session.add(ApiKey(name="ups", key_hash=await auth.hash_key_async(raw), key_prefix=raw[:8],
                          key_digest=None, scopes=["fire"], enabled=True, allowed_cidrs=[OFFICE]))
    await db_session.commit()
    with pytest.raises(HTTPException) as refused:
        await _resolve(raw, OUTSIDE)
    assert refused.value.status_code == 403
    assert _failures(OUTSIDE) == 1, "the reservation stands; not refunded, not counted twice"
    assert (await _resolve(raw, INSIDE)).name == "ups"
    assert _failures(INSIDE) == 0


async def test_a_refused_request_does_not_record_a_use(db_client, admin_key, db_session):
    from app.db.models import ApiKey as Row
    from tests._db import fresh

    created = await _key(db_client, admin_key, allowed_cidrs=[OFFICE])
    with pytest.raises(HTTPException):
        await _resolve(created["key"], OUTSIDE)
    await fresh(db_session)
    row = await db_session.get(Row, created["id"])
    assert row.last_used_at is None
    assert row.last_used_ip is None


@pytest.mark.parametrize(("cidr", "inside", "outside"), [
    ("2001:db8:10::/48", "2001:db8:10::5", "2001:db8:11::5"),
    ("192.0.2.0/24", "::ffff:192.0.2.9", "::ffff:198.51.100.1"),   # IPv4-mapped peers
])
async def test_ipv6_and_ipv4_mapped_addresses(db_client, admin_key, cidr, inside, outside):
    raw = (await _key(db_client, admin_key, allowed_cidrs=[cidr]))["key"]
    assert (await _resolve(raw, inside)).name == "script"
    auth.invalidate_key_cache()
    with pytest.raises(HTTPException):
        await _resolve(raw, outside)


async def test_without_an_address_a_restricted_key_is_refused(db_client, admin_key):
    raw = (await _key(db_client, admin_key, allowed_cidrs=[OFFICE]))["key"]
    with pytest.raises(HTTPException) as refused:
        await _resolve(raw, None)
    assert refused.value.status_code == 403


async def test_an_unrestricted_key_works_from_anywhere(db_client, admin_key):
    raw = (await _key(db_client, admin_key))["key"]
    assert (await _resolve(raw, OUTSIDE)).name == "script"


async def test_changing_the_list_takes_effect_on_the_next_request(db_client, admin_key):
    created = await _key(db_client, admin_key)
    await _resolve(created["key"], OUTSIDE)               # cached, unrestricted
    r = await db_client.patch(f"/v1/api_keys/{created['id']}", headers={"X-API-Key": admin_key},
                              json={"allowed_cidrs": [OFFICE]})
    assert r.status_code == 200, r.text
    with pytest.raises(HTTPException):
        await _resolve(created["key"], OUTSIDE)
    cleared = await db_client.patch(f"/v1/api_keys/{created['id']}", headers={"X-API-Key": admin_key},
                                    json={"allowed_cidrs": []})
    assert cleared.json()["allowed_cidrs"] == []
    assert (await _resolve(created["key"], OUTSIDE)).name == "script"


async def test_rotation_keeps_the_allowlist(db_client, admin_key):
    created = await _key(db_client, admin_key, allowed_cidrs=[OFFICE])
    rotated = (await db_client.post(f"/v1/api_keys/{created['id']}/rotate", headers={"X-API-Key": admin_key})).json()
    assert rotated["allowed_cidrs"] == [OFFICE]
    with pytest.raises(HTTPException):
        await _resolve(rotated["key"], OUTSIDE)


async def test_through_http_behind_a_trusted_proxy(db_client, admin_key, monkeypatch):
    """End to end: the real client address (X-Forwarded-For from a trusted
    proxy) is what the list is matched against."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_cidrs", "127.0.0.0/8")
    raw = (await _key(db_client, admin_key, allowed_cidrs=[OFFICE]))["key"]
    ok = await db_client.get("/v1/version", headers={"X-API-Key": raw, "X-Forwarded-For": INSIDE})
    fire_in = await db_client.post("/v1/fire", headers={"X-API-Key": raw, "X-Forwarded-For": INSIDE},
                                   json={"type": "t"})
    fire_out = await db_client.post("/v1/fire", headers={"X-API-Key": raw, "X-Forwarded-For": OUTSIDE},
                                    json={"type": "t"})
    assert ok.status_code == 200
    assert fire_in.status_code in (200, 202), fire_in.text
    assert fire_out.status_code == 403
    assert "not allowed from this address" in fire_out.text
