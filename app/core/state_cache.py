"""In-memory state cache — current values for all declared variables.

The cache is a dict ``{var_name: VarSnapshot}``. Reads/writes from
the asyncio loop are safe because Python dict ops are atomic at the
GIL level; concurrent updaters use no extra locking.

Subscribers (the WebSocket stream and the future rule evaluator)
register a callback via ``subscribe()``; they receive every value
update on the asyncio loop. The cache enforces a monotonic
timestamp guarantee — out-of-order MQTT messages are dropped (see
``docs/EDGE_CASES.md``).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VarSnapshot:
    """One entry in the cache."""

    value: Any
    ts: float                          # monotonic seconds (asyncio loop time)
    wall_ts: float                     # unix epoch seconds for display
    source_topic: str | None = None    # MQTT topic, HTTP URL, etc.
    source_kind: str = "unknown"
    # Variable-level staleness ceiling (from VarMapping.stale_after_sec
    # → Variable.config.stale_after_sec). None means "never stale" —
    # used by constants and aggregates without an explicit policy.
    # Audit H-4 (2026-05-14): the rule engine consults this so a stale
    # SOC reading cannot keep matching `soc < 20` after MQTT drops.
    stale_after_sec: float | None = None
    # Absolute monotonic deadline past which this value is stale (audit
    # B-04). For a direct value this is just ``ts + stale_after_sec``, but
    # a DERIVED value (aggregate / computed) sets it to its *evidence's*
    # deadline — the earliest contributing member's expiry, or the soonest
    # dependency expiry — so a derived result cannot outlive the data it
    # was built from even though its own recompute looks recent. None means
    # no evidence-based deadline (fall back to the age-based window below).
    expires_at: float | None = None

    def age_sec(self, now: float | None = None) -> float:
        """Seconds since this value was last refreshed (loop time)."""
        if now is None:
            now = time.monotonic()
        return now - self.ts

    def is_stale(self, now: float | None = None) -> bool:
        """True once this value's freshness has lapsed.

        Two independent bounds apply, and exceeding *either* makes it stale
        (audit B-04):

        * the age-based window — ``age > stale_after_sec`` — the classic
          "no update in N seconds" ceiling (audit H-4); and
        * the evidence deadline ``expires_at`` — set on derived values so an
          aggregate/computed result expires with the data behind it, not on
          its own (later) recompute time.

        Returns False only when neither bound is set (constants, schedule
        slots, ad-hoc writes without a policy)."""
        if now is None:
            now = time.monotonic()
        if self.stale_after_sec is not None and self.age_sec(now) > self.stale_after_sec:
            return True
        return self.expires_at is not None and now > self.expires_at


SubscribeFn = Callable[[str, VarSnapshot], Awaitable[None]]


class StateCache:
    """Live values for declared variables.

    Single instance per process — held by the input manager and
    queried by the rule evaluator (S4) and API endpoints.
    """

    def __init__(self) -> None:
        self._values: dict[str, VarSnapshot] = {}
        self._subscribers: list[SubscribeFn] = []
        # Optional convenience: track the last MQTT message ts (any
        # topic). /v1/health uses this for an MQTT freshness gauge.
        self._last_mqtt_ts: float | None = None

    # ── Reads ───────────────────────────────────────────────────────

    def get(self, name: str) -> VarSnapshot | None:
        return self._values.get(name)

    def value(self, name: str) -> Any:
        snap = self._values.get(name)
        return snap.value if snap is not None else None

    def snapshot(self) -> dict[str, VarSnapshot]:
        """Return a shallow copy — safe to iterate without holding a
        lock against a concurrent ``set``."""
        return dict(self._values)

    def known_names(self) -> set[str]:
        return set(self._values.keys())

    def last_mqtt_ts(self) -> float | None:
        return self._last_mqtt_ts

    # ── Writes ──────────────────────────────────────────────────────

    async def set(
        self,
        name: str,
        value: Any,
        *,
        source_topic: str | None = None,
        source_kind: str = "mqtt",
        stale_after_sec: float | None = None,
        expires_at: float | None = None,
    ) -> bool:
        """Write a value into the cache.

        Returns ``True`` if the write took effect (caller should fan
        out to subscribers, e.g., update aggregates). ``False`` if
        the value was discarded due to monotonic ts (out-of-order).

        ``stale_after_sec`` is a per-variable freshness ceiling
        propagated from VarMapping.stale_after_sec. Consumers (rule
        engine, /v1/variables) use VarSnapshot.is_stale() to gate
        on it. None = no policy (constants, ad-hoc writes).

        ``expires_at`` is an explicit monotonic evidence deadline for
        derived values (audit B-04). When omitted it defaults to
        ``ts + stale_after_sec`` (the age-based window), so a plain direct
        write behaves exactly as before; an aggregate/computed writer passes
        an earlier deadline so the result expires with its evidence.
        """
        now = time.monotonic()
        wall = time.time()
        existing = self._values.get(name)
        # Note on monotonic guarantee: we use loop monotonic time, not
        # broker timestamp, so out-of-order delivery within paho's
        # callback queue can never produce ts < existing.ts. This is
        # cheap protection against double-callback bugs.
        if existing is not None and now < existing.ts:
            logger.debug("Out-of-order ts for %s — dropping", name)
            return False

        if expires_at is None and stale_after_sec is not None:
            expires_at = now + stale_after_sec
        snap = VarSnapshot(
            value=value, ts=now, wall_ts=wall,
            source_topic=source_topic, source_kind=source_kind,
            stale_after_sec=stale_after_sec, expires_at=expires_at,
        )
        self._values[name] = snap
        if source_kind == "mqtt":
            self._last_mqtt_ts = now

        # Fan out to subscribers (WebSocket stream, future rule eval)
        if self._subscribers:
            await self._fanout(name, snap)
        return True

    def touch(
        self, name: str, now: float | None = None, *,
        expires_at: float | None = None,
    ) -> bool:
        """Refresh a snapshot's freshness timestamp in place without
        changing its value or fanning out to subscribers.

        Used when a computed variable re-evaluates to the *same* value but
        its dependencies are still fresh: the value is confirmed current, so
        its staleness clock must restart even though nothing changed (audit
        F08). The caller passes the recomputed evidence deadline so the
        value's ``expires_at`` tracks its dependencies rather than freezing
        at the first computation's deadline (audit B-04). Returns ``False``
        if the name is absent.
        """
        snap = self._values.get(name)
        if snap is None:
            return False
        snap.ts = time.monotonic() if now is None else now
        snap.wall_ts = time.time()
        snap.expires_at = expires_at
        return True

    # ── Subscribers ─────────────────────────────────────────────────

    def subscribe(self, fn: SubscribeFn) -> Callable[[], None]:
        """Register a coroutine to be called on every successful
        ``set``. Returns a cancel function.

        The callback is awaited sequentially per write — keep it
        cheap. If you need heavy work, schedule a background task."""
        self._subscribers.append(fn)

        def _cancel() -> None:
            try:
                self._subscribers.remove(fn)
            except ValueError:
                pass

        return _cancel

    async def _fanout(self, name: str, snap: VarSnapshot) -> None:
        # Snapshot the list to avoid mutation during iteration if a
        # subscriber unsubscribes itself
        for fn in list(self._subscribers):
            try:
                await fn(name, snap)
            except Exception:  # pragma: no cover — never break write path
                logger.exception("Subscriber raised; ignoring")

    # ── Reset (tests / admin reload) ────────────────────────────────

    def clear(self, *, only: set[str] | None = None) -> int:
        """Drop entries (entire cache or a subset). Used when input
        config changes invalidate previously-cached values."""
        if only is None:
            n = len(self._values)
            self._values.clear()
            self._last_mqtt_ts = None
            return n
        before = len(self._values)
        for k in only:
            self._values.pop(k, None)
        return before - len(self._values)


# ── Module singleton ──────────────────────────────────────────────


_global_cache: StateCache | None = None


def get_state_cache() -> StateCache:
    """Module accessor — single instance per process."""
    global _global_cache
    if _global_cache is None:
        _global_cache = StateCache()
    return _global_cache


def reset_state_cache_for_tests() -> None:
    """Pytest helper — replaces the singleton with a fresh one."""
    global _global_cache
    _global_cache = StateCache()
