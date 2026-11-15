"""Per-channel circuit breaker.

States:

- ``closed`` — normal operation. Counts consecutive failures.
- ``open`` — after ``threshold`` consecutive failures. All sends are
  short-circuited as ``circuit_open`` until ``open_until``.
- ``half_open`` — one trial send allowed; on success → closed,
  on failure → open again.

Configurable per process via ``settings.circuit_breaker_threshold``
and ``settings.circuit_breaker_open_sec``.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

State = Literal["closed", "open", "half_open"]


@dataclass
class BreakerState:
    state: State = "closed"
    consecutive_failures: int = 0
    open_until: float = 0.0     # monotonic seconds
    last_error: str | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None
    # True while a single half-open trial is reserved — so concurrent callers
    # don't all stampede a recovering provider (audit F37).
    probe_in_flight: bool = False


class CircuitBreaker:
    """One breaker per channel name. Owned by ChannelManager."""

    def __init__(self, *, threshold: int = 3, open_sec: int = 60) -> None:
        self._threshold = threshold
        self._open_sec = open_sec
        self._state: dict[str, BreakerState] = {}
        self._lock = asyncio.Lock()

    def state(self, name: str) -> BreakerState:
        return self._state.setdefault(name, BreakerState())

    async def allow(self, name: str) -> bool:
        """True if a send should be attempted; False if open. See :meth:`admit`."""
        return await self.admit(name) is not None

    async def admit(self, name: str) -> str | None:
        """``"send"`` (closed), ``"probe"`` (the half-open trial was reserved
        for this caller) or None (open: do not send).

        In ``half_open`` exactly one trial probe is admitted at a time
        (audit F37): the reservation is released by ``record_success`` /
        ``record_failure`` when the probe settles, or by ``release_probe``
        if the caller never attempts it (a rate-limit deferral, a cancelled
        dispatch — review K06)."""
        async with self._lock:
            s = self._state.setdefault(name, BreakerState())
            if s.state == "open":
                if time.monotonic() >= s.open_until:
                    s.state = "half_open"
                    s.probe_in_flight = True
                    return "probe"  # the single trial
                return None
            if s.state == "half_open":
                if s.probe_in_flight:
                    return None  # a trial is already in flight
                s.probe_in_flight = True
                return "probe"
            return "send"  # closed

    async def reset(self, name: str) -> None:
        """Force a breaker back to ``closed`` (manual operator action).

        Clears the open window and the consecutive-failure count so the
        next send is attempted immediately. Used by
        ``POST /v1/channels/{id}/breaker/reset`` after the operator has
        fixed the underlying cause (e.g. rotated a revoked token)."""
        async with self._lock:
            s = self._state.setdefault(name, BreakerState())
            s.state = "closed"
            s.consecutive_failures = 0
            s.open_until = 0.0
            s.probe_in_flight = False

    async def release_probe(self, name: str) -> None:
        """Release a reserved half-open probe the caller won't attempt
        (e.g. a rate-limit deferral), so a later caller can probe (F37)."""
        async with self._lock:
            s = self._state.setdefault(name, BreakerState())
            s.probe_in_flight = False

    async def record_success(self, name: str) -> None:
        async with self._lock:
            s = self._state.setdefault(name, BreakerState())
            s.consecutive_failures = 0
            s.last_success_at = time.monotonic()
            if s.state != "closed":
                from ..core.activity import record_event
                record_event(source_kind="channel", source_name=name, event="breaker_closed",
                             detail="a send succeeded; channel back in use")
            s.state = "closed"
            s.probe_in_flight = False

    async def record_failure(self, name: str, error: str) -> None:
        async with self._lock:
            s = self._state.setdefault(name, BreakerState())
            s.consecutive_failures += 1
            s.last_failure_at = time.monotonic()
            s.last_error = error[:200]
            s.probe_in_flight = False
            if s.consecutive_failures >= self._threshold:
                if s.state != "open":
                    from ..core.activity import record_event
                    record_event(source_kind="channel", source_name=name, event="breaker_open",
                                 detail=f"{s.consecutive_failures} failures in a row; paused {self._open_sec:.0f}s. Last: {s.last_error}")
                s.state = "open"
                s.open_until = time.monotonic() + self._open_sec

    def all_health(self) -> dict[str, dict]:
        """Per-channel breaker health for every known channel (audit F36)."""
        return {name: self.health(name) for name in list(self._state)}

    def health(self, name: str) -> dict:
        s = self._state.setdefault(name, BreakerState())
        return {
            "state": s.state,
            "consecutive_failures": s.consecutive_failures,
            "last_error": s.last_error,
            "last_success_at": s.last_success_at,
            "last_failure_at": s.last_failure_at,
            "reopens_in_sec": max(0, s.open_until - time.monotonic()) if s.state == "open" else 0,
        }
