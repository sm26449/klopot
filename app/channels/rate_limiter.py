"""Per-channel rate limit: at most N sends in any 60 seconds.

A sliding window of the last minute's send times per channel. That is the
guarantee a provider needs (an SMS gateway allowing N a minute) — stricter
than the API keys' GCRA limiter (``app.utils.rate_limit``), which lets a quiet
key burst N and then send one every 60/N s, close to 2N in the first minute.
Channel limits are small, so keeping the timestamps costs little.

``admit`` answers like the GCRA limiter (``Admission``): refused, it says how
long until a send fits — the oldest send that must leave the window — so a
held-back delivery is retried exactly then instead of after a fixed delay.

Single-process: channels in different processes each get their own limit
(Klopot runs one worker — Dockerfile).
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable

from ..utils.rate_limit import Admission

WINDOW_SEC = 60.0


class RateLimiter:
    """One instance per process; tracks all channels by name."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()
        self._clock = clock

    async def admit(self, name: str, limit_per_min: int) -> Admission:
        """Consume a slot if one is free; otherwise how long until one is.
        A limit of 0 (or less) is unlimited."""
        if limit_per_min <= 0:
            return Admission(True)
        async with self._lock:
            now = self._clock()
            win = self._windows.setdefault(name, deque())
            while win and win[0] <= now - WINDOW_SEC:
                win.popleft()
            if len(win) >= limit_per_min:
                # The send that has to leave the window for one more to fit —
                # not always the oldest: a lowered limit can leave more sends
                # in the window than it now allows.
                frees_at = win[len(win) - limit_per_min] + WINDOW_SEC
                return Admission(False, retry_after=max(0.0, frees_at - now))
            win.append(now)
            return Admission(True)

    async def allow(self, name: str, limit_per_min: int) -> bool:
        """True if under the limit (a slot is consumed); False if over."""
        return (await self.admit(name, limit_per_min)).allowed

    def used(self, name: str) -> int:
        """How many slots used in the last 60s (best-effort, no lock)."""
        win = self._windows.get(name)
        if not win:
            return 0
        cutoff = self._clock() - WINDOW_SEC
        return sum(1 for ts in win if ts > cutoff)
