"""The wrong-key budget holds under a burst, stays cheap, and keys on the real client (review K15).

- The budget was checked before hashing and spent only after it: a burst of
  concurrent wrong keys from one address all passed the check.
- Past 10,000 addresses, every wrong key from a new one rebuilt all of them
  on the event loop (~3 ms each).
- IPv6 hands every client a /64: one address per /128 was a free budget per
  request.
- The WebSocket ``?api_key=`` path counted the TCP peer — behind the proxy,
  every WebSocket client shared one budget.
- With every X-Forwarded-For hop trusted, the leftmost entry (the client's
  own claim) was taken as its address.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import HTTPException

from app import auth
from app.utils.client_ip import real_client_ip

pytestmark = pytest.mark.anyio


def _wrong(i: int) -> str:
    return f"alertd_wrong_key_number_{i:04d}_xxxxxxxx"


async def test_a_concurrent_burst_hashes_at_most_the_budget(db_session, admin_key, monkeypatch):
    hashed: list[bytes] = []

    async def slow(raw: bytes, _hashed: bytes) -> bool:
        hashed.append(raw)
        await asyncio.sleep(0.05)
        return False

    monkeypatch.setattr(auth, "_checkpw_async", slow)
    # Same bucket as the fixture admin key ("alertd_t"), so each guess is hashed.
    guesses = [f"alertd_t_guess_{i:03d}_xxxxxxxxxxxx" for i in range(30)]
    from app.db import session as session_module

    async def one(key: str) -> int:
        async with session_module._session_factory() as s:
            try:
                await auth._resolve_key(key, s, "203.0.113.50")
            except HTTPException as e:
                return e.status_code
        return 200

    codes = await asyncio.gather(*(one(k) for k in guesses))
    assert len(hashed) <= auth._KEY_BUDGET.max_failures, f"{len(hashed)} hashes for one address"
    assert codes.count(429) >= len(guesses) - auth._KEY_BUDGET.max_failures


async def test_a_right_key_is_not_charged(db_session, admin_key):
    from app.db import session as session_module

    for _ in range(auth._KEY_BUDGET.max_failures + 3):
        auth.invalidate_key_cache()
        async with session_module._session_factory() as s:
            await auth._resolve_key(admin_key, s, "203.0.113.51")
    assert not auth._KEY_BUDGET.spent("203.0.113.51")


def test_eviction_stays_cheap_past_the_address_cap(monkeypatch):
    monkeypatch.setattr(auth._KEY_BUDGET, "max_addresses", 2000)
    for i in range(2000):
        auth._KEY_BUDGET.note(f"10.{i // 250}.{i % 250}.1")
    started = time.perf_counter()
    for i in range(500):
        auth._KEY_BUDGET.note(f"192.0.{i // 250}.{i % 250}")
    per_call = (time.perf_counter() - started) / 500
    assert per_call < 0.0002, f"{per_call * 1000:.2f} ms per new address"
    assert len(auth._KEY_BUDGET) <= 2000


def test_ipv6_addresses_share_their_64():
    for i in range(auth._KEY_BUDGET.max_failures):
        auth._KEY_BUDGET.note(f"2001:db8:1:2::{i + 1:x}")
    assert auth._KEY_BUDGET.spent("2001:db8:1:2:ffff::9")
    assert not auth._KEY_BUDGET.spent("2001:db8:1:3::1")


def test_all_trusted_hops_fall_back_to_the_peer():
    # Every hop inside the trusted networks: the leftmost entry is the
    # client's own claim, so none is believed — the peer is used.
    trusted = ["10.0.0.0/8", "6.0.0.0/8"]
    assert real_client_ip("10.0.0.2", "6.6.6.6, 10.0.0.1", trusted) == "10.0.0.2"
    # A catch-all list, the case K15 first met, is now refused outright.
    with pytest.raises(ValueError, match="trusts every address"):
        real_client_ip("10.0.0.2", "6.6.6.6", ["0.0.0.0/0"])


async def test_the_websocket_counts_the_real_client(db_engine, monkeypatch):
    from types import SimpleNamespace

    from app.api.v1 import state as state_module
    from app.config import get_settings

    monkeypatch.setenv("ALERTD_TRUSTED_PROXY_CIDRS", "127.0.0.0/8")
    get_settings.cache_clear()
    seen: list[str | None] = []

    async def spy(raw, session, client_ip):
        seen.append(client_ip)
        raise HTTPException(401, "Invalid API key")

    class FakeSocket:
        def __init__(self) -> None:
            self.query_params = {"api_key": _wrong(1)}
            self.cookies: dict[str, str] = {}
            self.headers = {"x-forwarded-for": "198.51.100.77", "host": "alerts.example.com"}
            self.client = SimpleNamespace(host="127.0.0.1")
            self.closed: list[int] = []

        async def close(self, code: int, reason: str = "") -> None:
            self.closed.append(code)

    monkeypatch.setattr(state_module, "_resolve_key", spy)
    try:
        assert await state_module._ws_authenticate(FakeSocket()) is None
    finally:
        get_settings.cache_clear()
    assert seen == ["198.51.100.77"]
