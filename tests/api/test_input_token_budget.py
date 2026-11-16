"""Refused inbound requests are budgeted per address (review F3).

Input tokens are operator-chosen strings: without a bound, a dictionary
attack on `/v1/inputs/{id}/webhook` ran at network speed. A wrong or missing
token — and an id that is no live inbound input, the same 401 (F11) — counts
against the address: five a minute, then 429 for every request from it,
the right token included (otherwise a correct guess would still get in).
The budget is not the API keys': a sender with a stale token does not lock
out the keys used from the same address.
"""
from __future__ import annotations

import pytest

from app import auth

pytestmark = pytest.mark.anyio

TOKEN = "t" * 40


async def _hook(db_client, admin_key) -> int:
    r = await db_client.post("/v1/inputs", headers={"X-API-Key": admin_key}, json={
        "name": "hook", "kind": "webhook", "config": {"auth_token": TOKEN}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _post(db_client, input_id: int, token: str | None):
    headers = {"X-Input-Token": token} if token is not None else {}
    return await db_client.post(f"/v1/inputs/{input_id}/webhook", json={"v": 1}, headers=headers)


async def test_five_refusals_a_minute_then_429_for_everything(db_client, admin_key):
    hook = await _hook(db_client, admin_key)
    refused = [(await _post(db_client, hook, f"guess-{i}")).status_code for i in range(4)]
    refused.append((await _post(db_client, 987654, TOKEN)).status_code)        # no such input: counts too
    assert refused == [401] * 5
    blocked = await _post(db_client, hook, TOKEN)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert (await _post(db_client, hook, None)).status_code == 429


async def test_accepted_posts_spend_nothing(db_client, admin_key):
    hook = await _hook(db_client, admin_key)
    assert [(await _post(db_client, hook, TOKEN)).status_code for _ in range(10)] == [202] * 10


async def test_the_api_key_budget_is_separate(db_client, admin_key):
    hook = await _hook(db_client, admin_key)
    for i in range(5):
        await _post(db_client, hook, f"guess-{i}")
    assert (await _post(db_client, hook, TOKEN)).status_code == 429
    # Same address: the API keys still work, and their budget is untouched.
    assert (await db_client.get("/v1/channels", headers={"X-API-Key": admin_key})).status_code == 200
    assert auth._KEY_BUDGET.count("127.0.0.1") == 0


async def test_each_address_has_its_own_budget(db_client, admin_key, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_cidrs", "127.0.0.0/8")
    hook = await _hook(db_client, admin_key)
    for i in range(5):
        await db_client.post(f"/v1/inputs/{hook}/webhook", json={"v": 1},
                             headers={"X-Input-Token": f"guess-{i}", "X-Forwarded-For": "198.51.100.9"})
    other = await db_client.post(f"/v1/inputs/{hook}/webhook", json={"v": 1},
                                 headers={"X-Input-Token": TOKEN, "X-Forwarded-For": "203.0.113.7"})
    assert other.status_code == 202
