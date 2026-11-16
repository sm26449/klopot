"""A per-minute rate limit per key — GCRA, one number per key.

The generic cell rate algorithm keeps, for each key, the *theoretical
arrival time* (TAT): when the key would be back to a full allowance. A limit
of N a minute admits a request at ``now`` if, after it, the TAT is no more
than a minute ahead; each request moves the TAT forward by ``60 / N`` seconds.

So a key that has been quiet may send N at once, then one every ``60 / N``
seconds — the same steady rate as "N in any 60 s", without remembering every
request (the channel limiter's sliding window keeps a timestamp per send,
which a limit of thousands a minute would turn into thousands of entries per
key). A refusal knows exactly when the next request fits: that is the
``Retry-After``.

Pure and synchronous: the check and the update happen under one lock with no
``await`` in between, so concurrent requests cannot both take the last slot.
State lives in the process (Klopot runs one worker — Dockerfile) and a key at
its full allowance is the same as a key never seen, so pruning those loses
nothing.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass

WINDOW_SEC = 60.0
# Float slack: 7 requests of 60/7 s must add up to "within the minute".
_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class Admission:
    """The outcome of one request: admitted, or how long until one would be."""

    allowed: bool
    retry_after: float = 0.0


class PerMinuteLimiter:
    """Admit requests per key within ``per_minute`` (see the module docstring).

    ``max_idle`` bounds memory: past it, keys back at their full allowance are
    dropped (a key still being limited is never forgotten — that would lift
    its limit)."""

    def __init__(self, *, max_idle: int = 1024, clock: Callable[[], float] = time.monotonic) -> None:
        self._tat: dict[Hashable, float] = {}
        self._lock = threading.Lock()
        self._max_idle = max_idle
        self._clock = clock

    def admit(self, key: Hashable, per_minute: int) -> Admission:
        if per_minute <= 0:
            raise ValueError("per_minute must be positive")
        interval = WINDOW_SEC / per_minute
        with self._lock:
            now = self._clock()
            tat = max(self._tat.get(key, now), now) + interval
            if tat - now > WINDOW_SEC + _EPSILON:
                return Admission(False, retry_after=tat - WINDOW_SEC - now)
            self._tat[key] = tat
            if len(self._tat) > self._max_idle:
                self._prune(now)
            return Admission(True)

    def forget(self, key: Hashable | None = None) -> None:
        """Drop one key's state, or every key's (tests)."""
        with self._lock:
            if key is None:
                self._tat.clear()
            else:
                self._tat.pop(key, None)

    def _prune(self, now: float) -> None:
        for key in [k for k, tat in self._tat.items() if tat <= now]:
            del self._tat[key]
