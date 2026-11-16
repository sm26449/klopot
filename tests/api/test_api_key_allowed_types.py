"""Per-key allowed alert types (`api_keys.allowed_types`, migration 0044, review F10).

A key may be limited to template types or patterns (`backup_*`). POST
/v1/fire with another type — or naming another as the episode's
resolved_type — gets 403 TYPE_NOT_ALLOWED. Empty = every type, which every
existing key keeps. A change applies to the next request (the resolve cache
is invalidated), and rotation keeps the list.
"""
from __future__ import annotations

import pytest

from app import auth
from app.schemas.api_key import normalize_allowed_types


async def _key(db_client, admin_key, **body) -> dict:
    r = await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key},
                             json={"name": "backup-script", "scopes": ["fire"], **body})
    assert r.status_code == 201, r.text
    return r.json()


async def _fire(db_client, key: str, **body):
    return await db_client.post("/v1/fire", headers={"X-API-Key": key}, json={"context": {}, **body})


# ── Validation ────────────────────────────────────────────────────────


def test_entries_are_trimmed_and_deduplicated_in_order():
    assert normalize_allowed_types([" backup_* ", "disk_filling", "backup_*"]) == ["backup_*", "disk_filling"]


@pytest.mark.parametrize(("entries", "message"), [
    (["*"], "leave the list empty"), (["**?"], "leave the list empty"),
    (["Backup"], "not a template type"), (["a b"], "not a template type"),
    (["x" * 65], "not a template type"), ([f"t{i}" for i in range(65)], "at most 64"),
])
def test_invalid_lists_are_refused(entries, message):
    with pytest.raises(ValueError, match=message):
        normalize_allowed_types(entries)


async def test_the_api_stores_returns_and_clears_the_list(db_client, admin_key):
    created = await _key(db_client, admin_key, allowed_types=["backup_*", "backup_*"])
    assert created["allowed_types"] == ["backup_*"]
    h = {"X-API-Key": admin_key}
    r = await db_client.patch(f"/v1/api_keys/{created['id']}", headers=h, json={"allowed_types": []})
    assert r.json()["allowed_types"] == []          # empty = every type again
    r = await db_client.post("/v1/api_keys", headers=h, json={"name": "x", "scopes": ["fire"], "allowed_types": ["*"]})
    assert r.status_code == 422


# ── Enforcement ───────────────────────────────────────────────────────


async def test_a_limited_key_fires_its_types_and_nothing_else(db_client, admin_key):
    key = (await _key(db_client, admin_key, allowed_types=["backup_*", "disk_filling"]))["key"]
    assert (await _fire(db_client, key, type="backup_failed")).status_code == 202
    assert (await _fire(db_client, key, type="disk_filling")).status_code == 202
    refused = await _fire(db_client, key, type="server_down")
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "TYPE_NOT_ALLOWED"


async def test_a_limited_key_cannot_name_another_type_as_the_recovery(db_client, admin_key):
    key = (await _key(db_client, admin_key, allowed_types=["backup_*"]))["key"]
    r = await _fire(db_client, key, type="backup_failed", idempotency_key="nas-01", resolved_type="page_everyone")
    assert r.status_code == 403
    ok = await _fire(db_client, key, type="backup_failed", idempotency_key="nas-01", resolved_type="backup_ok")
    assert ok.status_code == 202


async def test_an_unlimited_key_fires_any_type(db_client, admin_key):
    key = (await _key(db_client, admin_key))["key"]
    assert (await _fire(db_client, key, type="anything_at_all")).status_code == 202


async def test_a_change_applies_to_the_next_request_and_rotation_keeps_it(db_client, admin_key):
    created = await _key(db_client, admin_key)
    key = created["key"]
    assert (await _fire(db_client, key, type="server_down")).status_code == 202   # now in the resolve cache
    h = {"X-API-Key": admin_key}
    await db_client.patch(f"/v1/api_keys/{created['id']}", headers=h, json={"allowed_types": ["backup_*"]})
    assert (await _fire(db_client, key, type="server_down")).status_code == 403
    rotated = (await db_client.post(f"/v1/api_keys/{created['id']}/rotate", headers=h)).json()
    assert rotated["allowed_types"] == ["backup_*"]
    assert (await _fire(db_client, rotated["key"], type="server_down")).status_code == 403


def test_may_fire_matches_names_and_patterns():
    actor = auth.Actor(kind="api_key", id=1, name="k", scopes=frozenset({"fire"}),
                       allowed_types=("backup_*", "disk_filling"))
    assert actor.may_fire("backup_failed") and actor.may_fire("disk_filling")
    assert not actor.may_fire("disk_filling_fast") and not actor.may_fire("server_down")
    assert auth.Actor(kind="user", id=1, name="u", scopes=frozenset({"admin"})).may_fire("anything")
