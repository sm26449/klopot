"""Per-channel rate limiter — sliding window over the last 60 seconds.

The check is independent of the circuit breaker. A channel with
``rate_limit_per_min=30`` allows up to 30 sends in any 60-second
window.

Implementation: keep a per-channel deque of send timestamps; on each
``allow()``, drop entries older than 60s and compare length against
the limit.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque


class RateLimiter:
    """One instance per process; tracks all channels by name."""

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, name: str, limit_per_min: int) -> bool:
        """True if under the limit; consumes a slot. False if over."""
        if limit_per_min <= 0:
            return True  # 0 = unlimited
        async with self._lock:
            now = time.monotonic()
            cutoff = now - 60.0
            win = self._windows.setdefault(name, deque())
            while win and win[0] < cutoff:
                win.popleft()
            if len(win) >= limit_per_min:
                return False
            win.append(now)
            return True

    def used(self, name: str) -> int:
        """How many slots used in the last 60s (best-effort, no lock)."""
        win = self._windows.get(name)
        if not win:
            return 0
        cutoff = time.monotonic() - 60.0
        return sum(1 for ts in win if ts >= cutoff)
