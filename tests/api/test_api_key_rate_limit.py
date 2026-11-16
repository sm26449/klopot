"""Per-key rate limit (`api_keys.rate_limit_per_min`, migration 0043).

A right key over its own limit gets 429 with the seconds until its next
request fits (Retry-After) — on every resolution path, HTTP and WebSocket
alike, since they all go through `auth._resolve_key`. It is not a wrong key:
the address's wrong-key budget is untouched. NULL = no limit, which every
existing key keeps.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth

pytestmark = pytest.mark.anyio

ADDR = "203.0.113.7"


async def _key(db_client, admin_key, **body) -> dict:
    r = await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key},
                             json={"name": "poller", "scopes": ["read"], **body})
    assert r.status_code == 201, r.text
    return r.json()


async def _get(db_client, raw: str):
    return await db_client.get("/v1/log?limit=1", headers={"X-API-Key": raw})


async def _resolve(raw: str):
    from app.db import session as session_module

    async with session_module._session_factory() as s:
        actor = await auth._resolve_key(raw, s, ADDR)
        await s.commit()
        return actor


@pytest.mark.parametrize("value", [0, -1, 60_001])
async def test_out_of_range_limits_are_refused(db_client, admin_key, value):
    r = await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key},
                             json={"name": "poller", "scopes": ["read"], "rate_limit_per_min": value})
    assert r.status_code == 422


async def test_over_the_limit_is_429_with_retry_after_and_not_a_wrong_key(db_client, admin_key):
    from app.metrics import API_KEY_RATE_LIMITED_TOTAL

    before = API_KEY_RATE_LIMITED_TOTAL.labels(key="poller")._value.get()
    raw = (await _key(db_client, admin_key, rate_limit_per_min=2))["key"]
    assert [(await _get(db_client, raw)).status_code for _ in range(2)] == [200, 200]
    refused = await _get(db_client, raw)
    assert refused.status_code == 429
    assert refused.json()["detail"] == "This API key is limited to 2 requests a minute"
    assert 1 <= int(refused.headers["retry-after"]) <= 30          # one slot every 30 s
    assert API_KEY_RATE_LIMITED_TOTAL.labels(key="poller")._value.get() == before + 1
    # A right key: no address's wrong-key budget moved, so another key still works.
    assert (await _get(db_client, admin_key)).status_code == 200
    assert not auth._KEY_BUDGET.spent("127.0.0.1")


async def test_the_resolve_cache_does_not_refill_the_allowance(db_client, admin_key):
    """A cache miss (digest path) and a cache hit spend the same allowance."""
    raw = (await _key(db_client, admin_key, rate_limit_per_min=2))["key"]
    await _resolve(raw)                                   # digest path, fills the cache
    auth.invalidate_key_cache()
    await _resolve(raw)                                   # digest path again
    with pytest.raises(HTTPException) as refused:
        await _resolve(raw)                               # cache hit
    assert refused.value.status_code == 429


async def test_each_key_has_its_own_allowance(db_client, admin_key):
    one = (await _key(db_client, admin_key, rate_limit_per_min=1))["key"]
    other = (await _key(db_client, admin_key, name="other", rate_limit_per_min=1))["key"]
    assert (await _get(db_client, one)).status_code == 200
    assert (await _get(db_client, one)).status_code == 429
    assert (await _get(db_client, other)).status_code == 200


async def test_without_a_limit_a_key_is_not_limited(db_client, admin_key):
    created = await _key(db_client, admin_key)
    assert created["rate_limit_per_min"] is None
    codes = [(await _get(db_client, created["key"])).status_code for _ in range(20)]
    assert codes == [200] * 20


async def test_editing_the_limit(db_client, admin_key):
    created = await _key(db_client, admin_key, rate_limit_per_min=1)
    url, h = f"/v1/api_keys/{created['id']}", {"X-API-Key": admin_key}
    assert (await _get(db_client, created["key"])).status_code == 200
    assert (await _get(db_client, created["key"])).status_code == 429
    # An unrelated edit leaves the limit, and does not refill the allowance.
    kept = await db_client.patch(url, headers=h, json={"enabled": True})
    assert kept.json()["rate_limit_per_min"] == 1
    assert (await _get(db_client, created["key"])).status_code == 429
    # Null removes it, on the next request.
    lifted = await db_client.patch(url, headers=h, json={"rate_limit_per_min": None})
    assert lifted.json()["rate_limit_per_min"] is None
    assert (await _get(db_client, created["key"])).status_code == 200


async def test_rotation_keeps_the_limit(db_client, admin_key):
    created = await _key(db_client, admin_key, rate_limit_per_min=5)
    rotated = (await db_client.post(f"/v1/api_keys/{created['id']}/rotate",
                                    headers={"X-API-Key": admin_key})).json()
    assert rotated["rate_limit_per_min"] == 5


async def test_a_websocket_handshake_spends_the_allowance(db_client, admin_key):
    """The stream authenticates through the same `_resolve_key`: a key over
    its limit cannot open streams either."""
    from types import SimpleNamespace

    from app.api.v1 import state as state_module

    raw = (await _key(db_client, admin_key, rate_limit_per_min=1))["key"]

    class FakeSocket:
        def __init__(self) -> None:
            self.query_params = {"api_key": raw}
            self.cookies: dict[str, str] = {}
            self.headers = {"host": "alerts.example.com"}
            self.client = SimpleNamespace(host=ADDR)
            self.closed: list[int] = []

        async def close(self, code: int, reason: str = "") -> None:
            self.closed.append(code)

    first, second = FakeSocket(), FakeSocket()
    assert (await state_module._ws_authenticate(first)) is not None
    assert await state_module._ws_authenticate(second) is None
    assert second.closed == [1008]
