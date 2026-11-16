"""An inbound input's own rate limit (config `rate_limit_per_min`).

Like an API key's: a sender with the right token over the limit gets 429
with Retry-After (one slot every 60/N s), checked after the token, so a
wrong token is still the 401 of the budget. Validated on save and import;
absent = no limit.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio

TOKEN = "r" * 40


def _h(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


async def _hook(db_client, admin_key, **config):
    return await db_client.post("/v1/inputs", headers=_h(admin_key), json={
        "name": "hook", "kind": "webhook", "config": {"auth_token": TOKEN, **config}})


async def _post(db_client, input_id: int, token: str = TOKEN):
    return await db_client.post(f"/v1/inputs/{input_id}/webhook", json={"v": 1}, headers={"X-Input-Token": token})


@pytest.mark.parametrize("value", [0, -5, 60_001, "10", 1.5, True])
async def test_invalid_limits_are_refused(db_client, admin_key, value):
    r = await _hook(db_client, admin_key, rate_limit_per_min=value)
    assert r.status_code == 422
    assert "rate_limit_per_min must be a whole number" in r.text


async def test_over_the_limit_is_429_with_retry_after(db_client, admin_key):
    hook = (await _hook(db_client, admin_key, rate_limit_per_min=2)).json()["id"]
    assert [(await _post(db_client, hook)).status_code for _ in range(2)] == [202, 202]
    over = await _post(db_client, hook)
    assert over.status_code == 429
    assert over.json()["detail"] == "This input takes at most 2 requests a minute"
    assert 1 <= int(over.headers["retry-after"]) <= 30
    # A wrong token is judged first: 401, not a spent allowance.
    assert (await _post(db_client, hook, "x" * 40)).status_code == 401


async def test_without_a_limit_the_input_is_not_limited(db_client, admin_key):
    hook = (await _hook(db_client, admin_key)).json()["id"]
    assert [(await _post(db_client, hook)).status_code for _ in range(10)] == [202] * 10


async def test_editing_the_limit_takes_effect_on_the_next_post(db_client, admin_key):
    created = (await _hook(db_client, admin_key, rate_limit_per_min=1)).json()
    assert (await _post(db_client, created["id"])).status_code == 202
    assert (await _post(db_client, created["id"])).status_code == 429
    r = await db_client.patch(f"/v1/inputs/{created['id']}", headers=_h(admin_key),
                              json={"config": {**created["config"], "rate_limit_per_min": None}})
    assert r.status_code == 200, r.text
    assert (await _post(db_client, created["id"])).status_code == 202


async def test_import_validates_the_limit(db_client, admin_key):
    pack = f"inputs:\n  - name: imp\n    kind: webhook\n    config: {{auth_token: {TOKEN}, rate_limit_per_min: 0}}\n"
    r = await db_client.post("/v1/config/import", params={"apply": "true"}, content=pack,
                             headers={**_h(admin_key), "Content-Type": "application/yaml"})
    assert "rate_limit_per_min must be a whole number" in r.text
