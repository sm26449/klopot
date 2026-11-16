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
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.activity import capture_exchanges, record_attempt
from ..db.models import Channel, ChannelActionToken, Delivery
from ..utils.redact import transport_error_text
from ..utils.time import utc_now
from . import REGISTRY, Notification
from ._secrets import channel_secret_strings, scrub_error
from .base import SendResult
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
    # For a deferral the upstream itself asked for (Retry-After): how long.
    defer_sec: dict[str, float] = field(default_factory=dict)
    # Failed for good (the adapter said so, e.g. a 4xx such as 422): no retries.
    permanent: set[str] = field(default_factory=set)
    provider_refs: dict[str, dict[str, Any]] = field(default_factory=dict)


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

    def output_health(self, name: str, kind: str) -> dict[str, Any]:
        adapter = self._adapter_instances.get(kind)
        if adapter is not None and hasattr(adapter, "health_for_channel"):
            return dict(adapter.health_for_channel(name))
        return {"attempted": False, "connected": False, "error": None}

    async def close(self) -> None:
        await asyncio.gather(*(adapter.close() for adapter in self._adapter_instances.values()))
        self._adapter_instances.clear()

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
            if ch.kind.value == "mqtt":
                from .mqtt_config import freeze_defaults

                cfg = freeze_defaults(cfg)
            if ch.kind.value == "telegram" and cfg.get("inline_actions") is True:
                from ._secrets import resolve_secret

                original = resolve_secret(ch.config or {}, "bot_token", "bot_token_ref")
                effective = resolve_secret(cfg, "bot_token", "bot_token_ref")
                if (ch.config or {}).get("inline_actions") is not True or cfg.get("chat_id") != (ch.config or {}).get("chat_id") or original != effective:
                    cfg["inline_actions"] = False
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
        """Send the notification to all named channels (see :meth:`_dispatch`).

        Any half-open probe this call reserved and did not settle is given back
        on the way out — also when the call is cancelled (the dispatcher bounds
        the first attempt with ``asyncio.wait_for``). Otherwise the channel
        stayed ``circuit_open`` until a restart (review K06).
        """
        probes: set[str] = set()
        try:
            return await self._dispatch(
                notif, channel_names, session, overrides_by_name, effective_by_name,
                effective_kind_by_name, outcome, probes,
            )
        finally:
            for name in probes:
                await self._breaker.release_probe(name)

    async def _dispatch(
        self,
        notif: Notification,
        channel_names: list[str],
        session: AsyncSession,
        overrides_by_name: dict[str, dict[str, Any] | None] | None,
        effective_by_name: dict[str, dict[str, Any] | None] | None,
        effective_kind_by_name: dict[str, str] | None,
        outcome: DispatchOutcome | None,
        probes: set[str],
    ) -> DispatchOutcome:
        """Send the notification to all named channels.

        ``probes`` collects the channels whose half-open probe this call holds
        and has not settled yet; :meth:`dispatch` releases what is left.

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
        telegram_names = [name for name, channel in by_name.items() if (effective_kind_by_name.get(name) or channel.kind.value) == "telegram"]
        delivery_rows = (await session.execute(select(Delivery).where(
            Delivery.idempotency_key.in_([f"{notif.id}:{name}"[:130] for name in telegram_names]),
        ))).scalars().all() if telegram_names else []
        deliveries_by_name = {d.channel: d for d in delivery_rows}
        # Activity log: which delivery row (and which attempt of it) each send is.
        attempt_ctx = {
            ch: (d_id, attempts, purpose)
            for d_id, ch, attempts, purpose in (await session.execute(
                select(Delivery.id, Delivery.channel, Delivery.attempts, Delivery.purpose).where(
                    Delivery.idempotency_key.in_([f"{notif.id}:{name}"[:130] for name in channel_names]))
            )).all()
        } if channel_names else {}
        active_tokens = set((await session.execute(select(ChannelActionToken.delivery_id).where(
            ChannelActionToken.delivery_id.in_([d.id for d in delivery_rows]),
            ChannelActionToken.used_at.is_(None), ChannelActionToken.expires_at > utc_now(),
        ))).scalars().all()) if delivery_rows else set()

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
            admission = await self._breaker.admit(name)
            if admission is None:
                outcome.deferred[name] = "circuit_open"
                record_attempt(channel=name, kind="alert", outcome="deferred", started_at=utc_now(), duration_ms=0,
                               exchange=None, notification_id=notif.id, error="not sent: circuit breaker open")
                continue
            if admission == "probe":
                probes.add(name)

            # Rate limiter — likewise a deferral, reschedule without an attempt.
            slot = await self._limiter.admit(name, ch.rate_limit_per_min)
            if not slot.allowed:
                # The breaker may have reserved a half-open probe for this
                # channel just above; release it since we won't send (F37).
                await self._breaker.release_probe(name)
                probes.discard(name)
                outcome.deferred[name] = "rate_limited"
                # Retry when a slot frees, not after the fixed deferral delay.
                outcome.defer_sec[name] = slot.retry_after
                record_attempt(channel=name, kind="alert", outcome="deferred", started_at=utc_now(), duration_ms=0,
                               exchange=None, notification_id=notif.id,
                               error=f"not sent: channel rate limit ({ch.rate_limit_per_min}/min)")
                continue

            to_dispatch.append((name, ch, adapter))

        # ── Parallel send (audit H-6) ──────────────────────────
        # Previously this loop awaited each channel's send()
        # sequentially → total latency = sum of all timeouts. With
        # Telegram (10s) + SMS (15s) + ui (instant), a single fire
        # could block ~28s, leaving the dispatcher transaction open
        # the whole time. Now each channel's send + breaker update
        # happens in a separate task; gather returns when ALL finish.
        async def _settle(name: str, ok: bool, err: str | None, *, breaker: bool = True) -> tuple[str, bool, str | None]:
            from ..metrics import DISPATCH_ATTEMPTS_TOTAL

            for outcome_name in ("ok", "failed"):
                DISPATCH_ATTEMPTS_TOTAL.labels(channel=name, outcome=outcome_name).inc(0)
            DISPATCH_ATTEMPTS_TOTAL.labels(channel=name, outcome="ok" if ok else "failed").inc()
            # Record the breaker result AND the outcome together, the moment the
            # channel settles — so a dispatch cancelled mid-flight still carries
            # the channels that already finished, and they are not re-sent (C-04).
            if ok:
                await self._breaker.record_success(name)
                outcome.succeeded.append(name)
            else:
                # A refusal of THIS message (breaker=False: a permanent 4xx) says
                # nothing about the channel's health — it must not trip the breaker.
                if breaker:
                    await self._breaker.record_failure(name, err or "unknown")
                else:
                    await self._breaker.release_probe(name)
                outcome.failed[name] = err or "unknown"
            # The record_* / release above settled any probe (no await between).
            probes.discard(name)
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
            if (effective_kind_by_name.get(name) or ch.kind.value) == "telegram":
                delivery = deliveries_by_name.get(name)
                cfg["_action_keyboard"] = delivery.action_keyboard if delivery and delivery.id in active_tokens else None
                cfg["_notification_id"] = delivery.notification_id if delivery else notif.id
            if (effective_kind_by_name.get(name) or ch.kind.value) == "mqtt":
                cfg["_channel_name"] = name
            # Stable per-delivery identity, identical on the first attempt and
            # every retry, matching the enqueue formula (audit F23).
            idem = f"{notif.id}:{name}"[:130]
            started_at, t0 = utc_now(), time.monotonic()
            d_id, d_attempts, d_purpose = attempt_ctx.get(name, (None, 0, None))
            # Every error kept from here on (delivery, log, activity) loses this
            # channel's secrets and URL path first: an upstream may echo them,
            # and readers with scope `read` must not get them (review K08).
            secrets: list[str] | None = None

            def _clean(text: Any) -> Any:
                nonlocal secrets
                if not isinstance(text, str) or not text:
                    return text
                if secrets is None:
                    secrets = channel_secret_strings(effective_kind_by_name.get(name) or ch.kind.value, cfg)
                return scrub_error(text, secrets)

            def _log_attempt(kind: str, err: str | None = None, res: SendResult | None = None) -> None:
                for entry in exchange:
                    for part in ("error", "request_body", "response_body"):
                        entry[part] = _clean(entry.get(part))
                err = _clean(err)
                ref = (res.response or {}).get("provider_ref") or (res.response or {}).get("message_id") if res else None
                record_attempt(
                    channel=name, kind="escalation" if d_purpose == "escalation" else "alert", outcome=kind,
                    started_at=started_at, duration_ms=int((time.monotonic() - t0) * 1000), exchange=exchange,
                    delivery_id=d_id, notification_id=notif.id, attempt_no=d_attempts + 1, error=err,
                    retry_after=res.retry_after if res else None, provider_ref=str(ref) if ref else None,
                )

            with capture_exchanges() as exchange:
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
                    _log_attempt("timeout", err)
                    return await _settle(name, False, err)
                except Exception as e:
                    # The exception text can embed a credential-bearing URL (R07).
                    err = _clean(f"adapter raised: {transport_error_text(e)}")[:200]
                    logger.exception("channel %s send failed", name)
                    _log_attempt("failed", err)
                    return await _settle(name, False, err)
            result.error = _clean(result.error)
            _log_attempt("sent" if result.ok else "deferred" if result.retry_after is not None
                         else "permanent" if result.permanent else "failed", result.error, result)
            if result.ok:
                if result.response and (
                    (effective_kind_by_name.get(name) or ch.kind.value) == "telegram"
                    or result.response.get("provider_ref")
                ):
                    outcome.provider_refs[name] = result.response
                return await _settle(name, True, None)
            if result.retry_after is not None:
                # Backpressure (429 / 503 + Retry-After): the upstream is healthy
                # and asked us to wait — defer by that long, like a rate-limit
                # denial (audit F22): no attempt spent, breaker untouched.
                await self._breaker.release_probe(name)
                probes.discard(name)
                outcome.deferred[name] = f"upstream asked to retry after {result.retry_after:.0f}s ({result.error or 'busy'})"[:200]
                outcome.defer_sec[name] = result.retry_after
                return (name, False, result.error)
            if result.permanent:
                outcome.permanent.add(name)
                return await _settle(name, False, result.error or "unknown", breaker=False)
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
