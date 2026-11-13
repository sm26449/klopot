"""Bounded thread-pool offload for synchronous crypto (audit A13).

bcrypt (API keys) and argon2 (admin passwords) are CPU- and memory-heavy
and were called synchronously inside async request handlers, blocking the
event loop for the whole hash/verify (~250 ms for bcrypt cost=12). Running
them in a worker thread frees the loop; a semaphore caps how many run at
once so an auth burst can't spawn unbounded threads or, for argon2, hold
many 64 MiB buffers at the same time.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

from ..config import get_settings

_T = TypeVar("_T")

# Lazily created so the bound honours settings and the semaphore binds to
# the running loop on first use (not at import time).
_sem: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(get_settings().hash_max_concurrency)
    return _sem


async def run_in_pool(fn: Callable[..., _T], *args: object) -> _T:
    """Run a blocking crypto function in a worker thread, bounded by the
    hashing concurrency semaphore."""
    async with _semaphore():
        return await asyncio.to_thread(fn, *args)


def reset_for_tests() -> None:
    """Drop the cached semaphore so a test can rebuild it with a different
    bound (or on a fresh event loop)."""
    global _sem
    _sem = None
