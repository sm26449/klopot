"""Tests for the bounded crypto offload pool (audit A13)."""
from __future__ import annotations

import asyncio
import threading
import time

from app.config import get_settings
from app.core import crypto_pool


async def test_run_in_pool_returns_result():
    assert await crypto_pool.run_in_pool(lambda: 1 + 1) == 2


async def test_run_in_pool_bounds_concurrency():
    """With the bound set to 2, no more than 2 offloaded calls may run at
    once even when 6 are launched together."""
    settings = get_settings()
    old = settings.hash_max_concurrency
    object.__setattr__(settings, "hash_max_concurrency", 2)
    crypto_pool.reset_for_tests()

    state = {"cur": 0, "max": 0}
    lock = threading.Lock()

    def work() -> None:
        with lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
        time.sleep(0.05)
        with lock:
            state["cur"] -= 1

    try:
        await asyncio.gather(*(crypto_pool.run_in_pool(work) for _ in range(6)))
        assert state["max"] <= 2
    finally:
        object.__setattr__(settings, "hash_max_concurrency", old)
        crypto_pool.reset_for_tests()
