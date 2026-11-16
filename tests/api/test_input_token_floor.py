"""An inbound input's token needs at least 32 characters (review F3).

Judged whenever the authentication is set or changed — create, an edit of
the token fields, an import that brings a different one. An input saved
before the floor keeps working: it can still be edited, disabled, exported
and restored as it is, and the API flags it (`token_too_short`) so the UI
can ask for a new token.
"""
from __future__ import annotations

import pytest

from app.db.models import Input, InputKind
from app.inputs.webhook import MIN_TOKEN_LENGTH

pytestmark = pytest.mark.anyio

LONG, SHORT = "k" * MIN_TOKEN_LENGTH, "k" * (MIN_TOKEN_LENGTH - 1)


def _h(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


async def _create(db_client, admin_key, config: dict, name: str = "hook"):
    return await db_client.post("/v1/inputs", headers=_h(admin_key),
                                json={"name": name, "kind": "webhook", "config": config})


async def test_a_new_input_needs_a_long_enough_token(db_client, admin_key):
    short = await _create(db_client, admin_key, {"auth_token": SHORT})
    assert short.status_code == 422
    assert "auth_token has 31 characters; an input token needs at least 32" in short.text
    created = await _create(db_client, admin_key, {"auth_token": LONG})
    assert created.status_code == 201
    assert created.json()["token_too_short"] is False


async def test_a_token_from_a_variable_is_judged_by_its_value(db_client, admin_key, monkeypatch):
    monkeypatch.setenv("KLOPOT_SECRET_SHORT_HOOK", SHORT)
    short = await _create(db_client, admin_key, {"auth_token_ref": "KLOPOT_SECRET_SHORT_HOOK"})
    assert short.status_code == 422
    assert "the variable KLOPOT_SECRET_SHORT_HOOK has 31 characters" in short.text
    # A variable that is not set yet cannot be judged; the input refuses
    # every post until it is.
    unset = await _create(db_client, admin_key, {"auth_token_ref": "KLOPOT_SECRET_NOT_YET"}, name="later")
    assert unset.status_code == 201


async def test_an_open_input_has_no_token_to_judge(db_client, admin_key):
    r = await _create(db_client, admin_key, {"auth_required": False})
    assert r.status_code == 201
    assert r.json()["token_too_short"] is False


async def test_an_input_saved_before_the_floor_works_is_flagged_and_stays_editable(db_client, admin_key, db_session):
    db_session.add(Input(name="legacy", kind=InputKind.webhook, enabled=True, config={"auth_token": SHORT}))
    await db_session.commit()
    listed = (await db_client.get("/v1/inputs", headers=_h(admin_key))).json()["items"]
    legacy = next(i for i in listed if i["name"] == "legacy")
    assert legacy["token_too_short"] is True
    url = f"/v1/inputs/{legacy['id']}"
    # Edits that leave the authentication as it is: allowed.
    assert (await db_client.patch(url, headers=_h(admin_key), json={"enabled": False})).status_code == 200
    masked_echo = await db_client.patch(url, headers=_h(admin_key), json={"config": legacy["config"]})
    assert masked_echo.status_code == 200, masked_echo.text
    # A new token is judged.
    shorter = await db_client.patch(url, headers=_h(admin_key), json={"config": {"auth_token": "k" * 10}})
    assert shorter.status_code == 422
    fixed = await db_client.patch(url, headers=_h(admin_key), json={"config": {"auth_token": "n" * 40}})
    assert fixed.status_code == 200
    assert fixed.json()["token_too_short"] is False


async def test_import_judges_only_a_token_it_changes(db_client, admin_key, db_session):
    db_session.add(Input(name="legacy", kind=InputKind.webhook, enabled=True, config={"auth_token": SHORT}))
    await db_session.commit()

    async def apply(pack: str):
        return await db_client.post("/v1/config/import", params={"apply": "true"}, content=pack,
                                    headers={**_h(admin_key), "Content-Type": "application/yaml"})

    # A restore of the input as it is: its old token is kept.
    same = await apply(f"inputs:\n  - name: legacy\n    kind: webhook\n    config: {{auth_token: {SHORT}}}\n")
    assert same.status_code == 200, same.text
    assert "needs at least" not in same.text
    # A new input, or another token: judged.
    new = await apply(f"inputs:\n  - name: fresh\n    kind: webhook\n    config: {{auth_token: {SHORT}}}\n")
    assert "needs at least 32" in new.text
    names = [i["name"] for i in (await db_client.get("/v1/inputs", headers=_h(admin_key))).json()["items"]]
    assert "fresh" not in names
