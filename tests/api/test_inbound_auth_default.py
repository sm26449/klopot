"""Inbound inputs require a token unless they say otherwise
(public-exposure review, High: Codex #1 / Claude F2).

A webhook / sms_inbox / alertmanager input without an `auth_required` flag
and without a token accepted posts from anyone, and the API saved such an
input without a word. Now: a token is required unless `auth_required` is the
boolean false; a config that requires a token without one is refused when it
is saved (REST create / update, config import); a disabled input answers like
a missing one; migration 0041 spells out the old behaviour of existing rows.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.inputs.webhook import auth_required, validate_inbound_auth, webhook_auth_ok

TOKEN = "a-long-enough-token-0123456789abcdef"


def _h(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


# ── The rule ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(("config", "required"), [
    ({}, True), ({"auth_token": TOKEN}, True), ({"auth_required": True}, True),
    ({"auth_required": False}, False),
    ({"auth_required": "false"}, True), ({"auth_required": 0}, True), ({"auth_required": None}, True),
])
def test_only_the_boolean_false_turns_authentication_off(config, required):
    assert auth_required(config) is required


@pytest.mark.parametrize(("config", "message"), [
    ({}, "needs a token"),
    ({"auth_required": True}, "needs a token"),
    ({"auth_required": "false"}, "true or false"),
    ({"auth_required": "yes", "auth_token": TOKEN}, "true or false"),
])
def test_a_config_that_cannot_authenticate_is_refused(config, message):
    with pytest.raises(ValueError, match=message):
        validate_inbound_auth(config)


@pytest.mark.parametrize("config", [
    {"auth_token": TOKEN}, {"auth_token_ref": "KLOPOT_SECRET_HOOK"}, {"auth_required": False},
])
def test_a_config_that_can_authenticate_is_accepted(config):
    validate_inbound_auth(config)


def test_required_without_a_token_rejects_everything():
    assert webhook_auth_ok({}, None) is False
    assert webhook_auth_ok({}, "guess") is False


# ── The API ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["webhook", "sms_inbox", "alertmanager"])
async def test_creating_an_inbound_input_without_a_token_is_refused(db_client, admin_key, kind):
    r = await db_client.post("/v1/inputs", headers=_h(admin_key), json={"name": f"in_{kind}", "kind": kind, "config": {}})
    assert r.status_code == 422, r.text
    assert "needs a token" in r.text


async def test_clearing_the_token_of_a_required_input_is_refused(db_client, admin_key):
    created = (await db_client.post("/v1/inputs", headers=_h(admin_key),
                                    json={"name": "hook", "kind": "webhook", "config": {"auth_token": TOKEN}})).json()
    r = await db_client.patch(f"/v1/inputs/{created['id']}", headers=_h(admin_key), json={"config": {"auth_token": ""}})
    assert r.status_code == 422, r.text
    # Echoing the masked token back keeps it: still valid.
    masked = created["config"]["auth_token"]
    ok = await db_client.patch(f"/v1/inputs/{created['id']}", headers=_h(admin_key), json={"config": {"auth_token": masked}})
    assert ok.status_code == 200, ok.text


async def test_an_explicitly_open_input_is_saved_and_takes_posts(db_client, admin_key):
    created = await db_client.post("/v1/inputs", headers=_h(admin_key),
                                   json={"name": "lan_device", "kind": "webhook", "config": {"auth_required": False}})
    assert created.status_code == 201, created.text
    r = await db_client.post(f"/v1/inputs/{created.json()['id']}/webhook", json={"v": 1})
    assert r.status_code == 202, r.text


async def test_a_disabled_input_looks_missing_even_with_the_right_token(db_client, admin_key):
    created = (await db_client.post("/v1/inputs", headers=_h(admin_key), json={
        "name": "paused", "kind": "webhook", "enabled": False, "config": {"auth_token": TOKEN}})).json()
    disabled = await db_client.post(f"/v1/inputs/{created['id']}/webhook", json={"v": 1}, headers={"X-Input-Token": TOKEN})
    missing = await db_client.post("/v1/inputs/987654/webhook", json={"v": 1}, headers={"X-Input-Token": TOKEN})
    assert disabled.status_code == 401
    assert disabled.json() == missing.json()


async def test_import_applies_the_same_rule(db_client, admin_key):
    pack = "inputs:\n  - name: imported_hook\n    kind: webhook\n    config: {}\n"
    r = await db_client.post("/v1/config/import", params={"apply": "true"}, content=pack,
                             headers={**_h(admin_key), "Content-Type": "application/yaml"})
    assert "needs a token" in r.text
    names = [i["name"] for i in (await db_client.get("/v1/inputs", headers=_h(admin_key))).json()["items"]]
    assert "imported_hook" not in names


# ── Migration 0041 keeps every existing input's behaviour ─────────────


def _migration():
    path = next(Path("alembic/versions").glob("*_0041_inbound_auth_explicit.py"))
    spec = importlib.util.spec_from_file_location("m0041", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("before", "after"), [
    ({}, {"auth_required": False}),                                   # was open → open, now visibly
    ({"auth_token": TOKEN}, None),                                    # was required → unchanged
    ({"auth_token_ref": "X"}, None),
    ({"auth_required": "false", "auth_token": TOKEN}, {"auth_required": True, "auth_token": TOKEN}),  # old bool("false")
    ({"auth_required": False}, None),
])
def test_migration_0041_spells_out_the_old_behaviour(before, after):
    assert _migration()._explicit(before) == after
    # …and under the new rule each result behaves as the old code did.
    result = after if after is not None else before
    old = bool(before["auth_required"]) if "auth_required" in before else bool(before.get("auth_token") or before.get("auth_token_ref"))
    assert auth_required(result) is old
