"""Channel manager — orchestrates dispatch with breaker + rate limit.

The dispatcher hands off ``(notification, channel_names, session)``;
this module:

  1. Loads channel rows from DB (cached briefly)
  2. For each channel:
     - Check circuit breaker — if open, mark as failed (circuit_open)
     - Check rate limiter — if over, mark as failed (rate_limited)
     - Look up adapter from ``REGISTRY[kind]``
     - Call ``adapter.send(notif, channel.config)``
     - Record success/failure in breaker
  3. Return a ``DispatchOutcome`` with per-channel results

Errors don't propagate — every failure becomes a recorded
``failed_channels[name] = "<reason>"`` in the log row. The dispatcher
takes the outcome and writes it to ``notifications_log``.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models import Channel
from ..utils.redact import redact_url
from . import REGISTRY, Notification
from .circuit_breaker import CircuitBreaker
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class DispatchOutcome:
    """Per-channel results for one notification."""

    succeeded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    # Channels denied scheduling (circuit open / rate-limited) — the
    # transport was never attempted, so these are DEFERRED, not failed, and
    # must be rescheduled without burning a retry attempt (audit F22).
    deferred: dict[str, str] = field(default_factory=dict)


class ChannelManager:
    """Single instance per process."""

    # How often the breaker-state publisher snapshots its CB
    # internals into the state cache. 30s is fine-grained enough
    # for a 5-min "channel down too long" rule and cheap enough
    # not to matter (a few dict reads, N writes).
    _BREAKER_PUBLISH_INTERVAL_SEC: float = 30.0

    def __init__(self) -> None:
        s = get_settings()
        self._breaker = CircuitBreaker(
            threshold=s.circuit_breaker_threshold,
            open_sec=s.circuit_breaker_open_sec,
        )
        self._limiter = RateLimiter()
        self._adapter_instances: dict[str, Any] = {}  # kind → adapter instance
        self._publisher_task: asyncio.Task[None] | None = None
        self._publisher_stop: asyncio.Event = asyncio.Event()

    # ── Breaker-state publisher (audit M-8) ──────────────────────
    # Periodically writes each channel's breaker state into the
    # state cache so the rule engine can fire on stuck-open
    # channels (e.g. revoked Telegram bot token). Without this,
    # operators discover broken channels only by accident.

    async def start_breaker_publisher(self) -> None:
        """Start the background task. Idempotent — second call is a
        no-op. Lifecycle owned by FastAPI lifespan."""
        if self._publisher_task is not None:
            return
        self._publisher_stop.clear()
        self._publisher_task = asyncio.create_task(
            self._run_breaker_publisher(),
            name="channel-breaker-publisher",
        )

    async def stop_breaker_publisher(self) -> None:
        self._publisher_stop.set()
        if self._publisher_task is not None:
            self._publisher_task.cancel()
            try:
                await self._publisher_task
            except (asyncio.CancelledError, Exception):
                pass
            self._publisher_task = None

    async def _run_breaker_publisher(self) -> None:
        from ..core.state_cache import get_state_cache
        cache = get_state_cache()
        while not self._publisher_stop.is_set():
            try:
                await self._snapshot_breakers_to_cache(cache)
            except Exception:
                logger.exception("breaker publisher snapshot failed")
            try:
                await asyncio.wait_for(
                    self._publisher_stop.wait(),
                    timeout=self._BREAKER_PUBLISH_INTERVAL_SEC,
                )
            except TimeoutError:
                pass

    async def _snapshot_breakers_to_cache(self, cache) -> None:
        """Write `channel.<name>.breaker_state` for every known
        channel into the state cache. State is a string
        ('closed'/'open'/'half_open'); rule can use ==.

        We also expose `channel.<name>.consecutive_failures` so a
        rule can gate on "failure rate is high but not yet open".

        ``stale_after_sec`` is set to 5×publish interval so a rule
        using `var_age()` against these names doesn't fire false
        positives during a normal publish cycle.
        """
        import time as _time
        ttl = self._BREAKER_PUBLISH_INTERVAL_SEC * 5
        now = _time.monotonic()
        # Iterate the breaker's known channels. Internal: relies on
        # CircuitBreaker._state, but adapter is in the same package.
        for name, st in list(self._breaker._state.items()):
            if st.open_until and now < st.open_until:
                state_str = "open"
            elif st.consecutive_failures > 0:
                state_str = "half_open"
            else:
                state_str = "closed"
            await cache.set(
                f"channel.{name}.breaker_state", state_str,
                source_topic=None, source_kind="internal",
                stale_after_sec=ttl,
            )
            await cache.set(
                f"channel.{name}.consecutive_failures",
                float(st.consecutive_failures),
                source_topic=None, source_kind="internal",
                stale_after_sec=ttl,
            )

    def _get_adapter(self, kind: str) -> Any:
        """Lazy-instantiate adapters, one per kind per process."""
        if kind not in self._adapter_instances:
            cls = REGISTRY.get(kind)
            if cls is None:
                return None
            self._adapter_instances[kind] = cls()
        return self._adapter_instances[kind]

    async def resolve_effective_configs(
        self,
        session: AsyncSession,
        channel_names: list[str],
        overrides_by_name: dict[str, dict[str, Any] | None] | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Freeze each channel's effective send config AND adapter kind NOW
        (audit V01 + B-02).

        The channel's own config shallow-merged with the per-route override, plus
        the channel's adapter kind, resolved once at fire time. The dispatcher
        stores both on each delivery so every retry targets the same destination
        **through the same adapter**, even if the channel is edited or repurposed
        meanwhile. Channels that don't resolve (not found) are simply omitted —
        the dispatch path reports them. Returns ``(configs, kinds)`` keyed by
        channel name.
        """
        overrides_by_name = overrides_by_name or {}
        if not channel_names:
            return {}, {}
        rows = (
            await session.execute(
                select(Channel).where(Channel.name.in_(channel_names))
            )
        ).scalars().all()
        by_name = {c.name: c for c in rows}
        configs: dict[str, dict[str, Any]] = {}
        kinds: dict[str, str] = {}
        for name in channel_names:
            ch = by_name.get(name)
            if ch is None:
                continue
            cfg = dict(ch.config or {})
            override = overrides_by_name.get(name)
            if override:
                cfg.update(override)
            configs[name] = cfg
            kinds[name] = ch.kind.value
        return configs, kinds

    async def dispatch(
        self,
        notif: Notification,
        channel_names: list[str],
        session: AsyncSession,
        overrides_by_name: dict[str, dict[str, Any] | None] | None = None,
        effective_by_name: dict[str, dict[str, Any] | None] | None = None,
        effective_kind_by_name: dict[str, str] | None = None,
        outcome: DispatchOutcome | None = None,
    ) -> DispatchOutcome:
        """Send the notification to all named channels.

        ``effective_by_name`` carries the full effective send config frozen at
        enqueue time (audit V01), and ``effective_kind_by_name`` the adapter kind
        frozen then (audit B-02); when present for a channel the config is used
        verbatim and the adapter is chosen from the frozen kind, so a retry
        targets the SAME destination THROUGH THE SAME ADAPTER as the first
        attempt even if the channel was edited or repurposed. Otherwise the
        legacy path applies ``overrides_by_name`` — per-route
        ``channel_overrides`` (audit A34) shallow-merged over the channel's live
        config, with the adapter taken from the live channel kind.

        A caller may pass a pre-made ``outcome``: each channel's result is written
        to it as soon as that channel settles, so a caller that cancels the
        dispatch on an overall timeout (the sync first-attempt budget) can still
        read which channels actually succeeded and must not be re-sent (C-04).
        """
        if outcome is None:
            outcome = DispatchOutcome()
        if not channel_names:
            return outcome
        overrides_by_name = overrides_by_name or {}
        effective_by_name = effective_by_name or {}
        effective_kind_by_name = effective_kind_by_name or {}

        # Load channel rows by name in one query
        rows = (
            await session.execute(
                select(Channel).where(Channel.name.in_(channel_names))
            )
        ).scalars().all()
        by_name = {c.name: c for c in rows}

        # ── Pre-validate channels (cheap, do sequentially) ─────
        # Sets `outcome.failed[name]` immediately for any channel
        # that can't even attempt a send. The remaining channels go
        # into ``to_dispatch`` for parallel send below.
        to_dispatch: list[tuple[str, Channel, Any]] = []
        for name in channel_names:
            ch = by_name.get(name)
            if ch is None:
                outcome.failed[name] = "channel not found"
                continue
            if not ch.enabled:
                outcome.failed[name] = "channel disabled"
                continue

            # Pick the adapter from the kind FROZEN at enqueue when we have one
            # (audit B-02), so a channel repurposed after enqueue (webhook → ui)
            # still delivers its already-admitted messages through the original
            # adapter + frozen config, instead of feeding that config to a
            # different adapter that would falsely report success. Legacy rows
            # (no frozen kind) fall back to the live channel kind.
            kind = effective_kind_by_name.get(name) or ch.kind.value
            adapter = self._get_adapter(kind)
            if adapter is None:
                outcome.failed[name] = f"no adapter for kind={kind}"
                continue

            # Circuit breaker — a denial is a deferral, not a transport
            # failure (audit F22): the message never reached the adapter.
            if not await self._breaker.allow(name):
                outcome.deferred[name] = "circuit_open"
                continue

            # Rate limiter — likewise a deferral, reschedule without an attempt.
            if not await self._limiter.allow(name, ch.rate_limit_per_min):
                # The breaker may have reserved a half-open probe for this
                # channel just above; release it since we won't send (F37).
                await self._breaker.release_probe(name)
                outcome.deferred[name] = "rate_limited"
                continue

            to_dispatch.append((name, ch, adapter))

        # ── Parallel send (audit H-6) ──────────────────────────
        # Previously this loop awaited each channel's send()
        # sequentially → total latency = sum of all timeouts. With
        # Telegram (10s) + SMS (15s) + ui (instant), a single fire
        # could block ~28s, leaving the dispatcher transaction open
        # the whole time. Now each channel's send + breaker update
        # happens in a separate task; gather returns when ALL finish.
        async def _settle(name: str, ok: bool, err: str | None) -> tuple[str, bool, str | None]:
            # Record the breaker result AND the outcome together, the moment the
            # channel settles — so a dispatch cancelled mid-flight still carries
            # the channels that already finished, and they are not re-sent (C-04).
            if ok:
                await self._breaker.record_success(name)
                outcome.succeeded.append(name)
            else:
                await self._breaker.record_failure(name, err or "unknown")
                outcome.failed[name] = err or "unknown"
            return (name, ok, err)

        async def _send_one(name: str, ch, adapter) -> tuple[str, bool, str | None]:
            # Prefer the full effective config frozen at enqueue (audit V01)
            # so every retry targets the same destination. Fall back to the
            # legacy live merge (audit A34) for rows enqueued before V01.
            frozen = effective_by_name.get(name)
            if frozen is not None:
                cfg = dict(frozen)
            else:
                cfg = dict(ch.config or {})
                route_override = overrides_by_name.get(name)
                if route_override:
                    cfg.update(route_override)
            # Stable per-delivery identity, identical on the first attempt and
            # every retry, matching the enqueue formula (audit F23).
            idem = f"{notif.id}:{name}"[:130]
            try:
                # Hard ceiling so a hung send can't stall the dispatcher / worker
                # or wedge a half-open breaker probe (audit C-01, C-02). The
                # adapter's own HTTP timeout normally fires first; this is the
                # backstop when it doesn't.
                async with asyncio.timeout(get_settings().adapter_send_timeout_sec):
                    result = await adapter.send(notif, cfg, idempotency_key=idem)
            except TimeoutError:
                err = f"send timed out after {get_settings().adapter_send_timeout_sec:.0f}s"
                logger.warning("channel %s send timed out", name)
                return await _settle(name, False, err)
            except Exception as e:
                # The exception text can embed a credential-bearing URL (R07).
                err = redact_url(f"adapter raised: {type(e).__name__}: {e}")[:200]
                logger.exception("channel %s send failed", name)
                return await _settle(name, False, err)
            if result.ok:
                return await _settle(name, True, None)
            return await _settle(name, False, result.error or "unknown")

        if to_dispatch:
            results = await asyncio.gather(
                *(_send_one(n, c, a) for n, c, a in to_dispatch),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, BaseException):
                    # Defensive: gather shouldn't reach here because _send_one
                    # catches everything (results are recorded in _settle).
                    logger.exception("unexpected exception in dispatch task: %r", r)

        return outcome

    async def reset_breaker(self, name: str) -> dict[str, Any]:
        """Force a channel's circuit breaker closed and return its new
        health. Exposed via ``POST /v1/channels/{id}/breaker/reset``."""
        await self._breaker.reset(name)
        return self._breaker.health(name)

    def health(self, name: str | None = None) -> dict[str, Any]:
        """If name given, return that channel's breaker state.
        Otherwise overall stats."""
        if name is not None:
            return {
                "breaker": self._breaker.health(name),
                "rate_used": self._limiter.used(name),
            }
        return {
            "adapter_kinds_loaded": list(self._adapter_instances.keys()),
        }

    def breaker_states(self) -> dict[str, dict[str, Any]]:
        """Per-channel breaker health, for metrics export (audit F36).

        ``health(None)`` returns loaded adapter *kinds*, not per-channel
        health, so the metrics refresh must iterate this instead."""
        return self._breaker.all_health()


# ── Module singleton ──────────────────────────────────────────────


_manager: ChannelManager | None = None


def get_channel_manager() -> ChannelManager:
    global _manager
    if _manager is None:
        _manager = ChannelManager()
    return _manager
