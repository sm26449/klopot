"""Input manager — wires DB-declared inputs + variables to runtime
adapters and the state cache.

Lifecycle (called from FastAPI lifespan):

    manager = InputManager()
    await manager.start()      # reads DB, starts adapters
    ...
    await manager.stop()

Hot reload: ``await manager.reload()`` re-reads DB and updates the
adapters' filter sets atomically. Called when admin POSTs to
``/v1/inputs`` or ``/v1/variables``.

The manager handles ``mqtt`` inputs and all variable sources: ``mqtt``,
``aggregate``, ``constant``, ``computed`` (recomputed on dependency
change) and ``schedule`` (driven by a clock tick here). See audit A15.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..db.models import Input, Variable
from ..inputs import REGISTRY, BaseInput
from ..schemas.common import VariableSource
from .staleness import effective_stale_after_sec
from .state_cache import StateCache, get_state_cache
from .variable_resolver import VariableResolver, VarMapping

logger = logging.getLogger(__name__)


class InputManager:
    """One per process. Owns input adapters + the resolver."""

    # How often schedule variables are evaluated against the clock. Cron
    # resolution is one minute, so a sub-minute tick never misses a fire.
    _SCHEDULE_TICK_SEC = 15.0

    def __init__(self) -> None:
        self._cache: StateCache = get_state_cache()
        self._resolver = VariableResolver(self._cache)
        self._adapters: dict[str, BaseInput] = {}  # by input.name
        # Last seen (connected, error) per input — activity-log transitions.
        self._input_state: dict[str, tuple[bool, str | None]] = {}
        self._started: bool = False
        self._sched_task: asyncio.Task[None] | None = None
        # Serialize reloads so two concurrent CRUD-triggered reloads can't
        # interleave across awaits and install an older DB snapshot over a
        # newer one (audit R03).
        self._reload_lock = asyncio.Lock()

    @property
    def cache(self) -> StateCache:
        return self._cache

    @property
    def resolver(self) -> VariableResolver:
        return self._resolver

    def adapter_health(self) -> dict[str, dict[str, Any]]:
        # Augment each adapter's own snapshot with kind + critical so
        # /v1/health can weight critical inputs separately (a non-critical
        # input down must not degrade overall service health).
        return {
            name: {**a.health(), "kind": a.kind, "critical": a.critical}
            for name, a in self._adapters.items()
        }

    def get_adapter(self, name: str) -> BaseInput | None:
        """Return a running adapter by input name (used by the
        webhook receiver endpoint)."""
        return self._adapters.get(name)

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        async for s in get_session():
            await self._load(s)
            break  # get_session is a generator — single iteration
        # Drive schedule variables off the clock (audit A15).
        self._sched_task = asyncio.create_task(
            self._schedule_loop(), name="variable-schedules",
        )

    async def stop(self) -> None:
        if not self._started:
            return
        if self._sched_task is not None:
            self._sched_task.cancel()
            try:
                await self._sched_task
            except asyncio.CancelledError:
                pass
            self._sched_task = None
        for adapter in list(self._adapters.values()):
            try:
                await adapter.stop()
            except Exception:
                logger.exception("stop adapter %s", adapter.name)
        self._adapters.clear()
        self._started = False

    async def _schedule_loop(self) -> None:
        """Periodic clock tick for ``schedule`` variables (audit A15) and
        derived-value freshness (audit B-04)."""
        from ..config import get_settings
        tz = ZoneInfo(get_settings().tz)
        while True:
            try:
                await asyncio.sleep(self._SCHEDULE_TICK_SEC)
                await self._resolver.evaluate_schedules(datetime.now(tz))
                # B-04: expire derived values on the clock, not only on inbound
                # messages — an aggregate whose member went silent, or a
                # computed whose dependency's TTL lapsed, must stop looking
                # fresh even when nothing new arrives.
                await self._resolver.sweep()
                self._note_input_transitions()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - never kill the loop
                logger.exception("schedule evaluation tick failed")

    def _note_input_transitions(self) -> None:
        """Activity log: an input connecting, dropping or erroring — recorded
        on the change only, never per tick (docs/ACTIVITY_LOG.md)."""
        from .activity import record_event

        seen = self._input_state
        for name, a in list(self._adapters.items()):
            h = a.health()
            now = (bool(h.get("connected")), h.get("error") or None)
            before = seen.get(name)
            seen[name] = now
            if before == now or (before is None and now[0]):
                continue  # unchanged, or healthy at first sight
            if now[0]:
                event = "recovered" if before and before[1] else "connected"
            else:
                event = "error" if now[1] else "disconnected"
            record_event(source_kind="input", source_name=name, event=event, detail=now[1],
                         source_id=getattr(a, "input_id", None))
        for gone in set(seen) - set(self._adapters):
            seen.pop(gone, None)

    async def reload(self) -> None:
        """Hot reload — re-read DB, update resolver + adapter filters,
        start/stop adapters as needed.

        Called from API handlers after CRUD on inputs/variables.
        Idempotent. Adapters whose config didn't change keep their
        connections. Serialized so concurrent reloads can't install a stale
        snapshot (audit R03); each acquires the latest committed DB state."""
        async with self._reload_lock:
            async for s in get_session():
                await self._load(s, reload=True)
                break

    async def force_restart(self, name: str) -> bool:
        """Stop and reconstruct a single named adapter regardless of config
        equality (audit F13).

        Ordinary ``reload`` keeps an adapter whose config is unchanged, so a
        crashed or stopped adapter would never actually restart. This stops
        the current instance (if any) and drops it, then reloads so it is
        rebuilt from the DB. Returns ``True`` if the adapter is running after
        the rebuild.
        """
        existing = self._adapters.pop(name, None)
        if existing is not None:
            try:
                await existing.stop()
            except Exception:
                logger.exception("force_restart: stop %s", name)
        await self.reload()
        return name in self._adapters

    # ── Internals ──────────────────────────────────────────────────

    def _on_value_for(self, input_id: int) -> Any:
        """Build the per-adapter ``on_value`` callback, binding this
        input's id so the resolver can isolate updates to variables
        actually bound to this input (audit A32)."""
        async def _cb(topic: str, payload: Any, source_kind: str) -> None:
            await self._resolver.handle_inbound(
                topic, payload, source_kind, input_id=input_id,
            )
        return _cb

    async def _load(self, session: AsyncSession, reload: bool = False) -> None:
        """Read inputs + variables from DB, sync adapters, update
        resolver, push topic filters to adapters."""
        inputs = (
            await session.execute(select(Input).where(Input.enabled.is_(True)))
        ).scalars().all()
        variables = (
            await session.execute(select(Variable).where(Variable.enabled.is_(True)))
        ).scalars().all()

        # Build mappings → resolver
        mappings = [_var_to_mapping(v) for v in variables]
        mappings = [m for m in mappings if m is not None]
        invalidated = self._resolver.replace_mappings(mappings)
        # The history computed formulas look back on (ADR-0004).
        from .history import get_history_store, merge_needs
        get_history_store().set_needs("computed", merge_needs(
            m.formula for m in mappings if m is not None and m.source == "computed"))
        await self._resolver.seed_constants()
        # Seed computed variables whose dependencies are already known
        # (e.g. constants), so they have a value before the first message.
        await self._resolver.recompute_computed()
        # B-03: an aggregate whose binding changed had its cached output
        # invalidated by the swap. Recompute it from the members we retained
        # so its value is consistent right after the reload, rather than
        # reading None until the next member message arrives. Aggregates with
        # an unchanged binding keep both their buffer and their output
        # untouched, so this never resets a healthy aggregate's freshness.
        agg_invalidated = {
            m.name for m in mappings
            if m is not None and m.source == "aggregate" and m.name in invalidated
        }
        if agg_invalidated:
            await self._resolver.recompute_aggregates(only=agg_invalidated)

        # Sync adapters: stop removed, start new, update existing.
        # Wanted = all inputs whose kind is in REGISTRY.
        wanted: dict[str, Input] = {
            i.name: i for i in inputs if i.kind.value in REGISTRY
        }
        for i in inputs:
            if i.enabled and i.kind.value not in REGISTRY:
                # Never runs (no adapter): say so instead of an input whose
                # health just stays empty (Copilot hygiene #5).
                logger.warning("input %r: kind %r has no adapter and is not started", i.name, i.kind.value)
        # Stop removed
        for name in list(self._adapters.keys()):
            if name not in wanted:
                try:
                    await self._adapters[name].stop()
                except Exception:
                    logger.exception("stop %s", name)
                del self._adapters[name]
                logger.info("Adapter %s removed", name)

        # Start / update kept
        for name, row in wanted.items():
            kind_str = row.kind.value
            new_config = dict(row.config or {})
            wanted_cls = REGISTRY.get(kind_str)
            if wanted_cls is None:
                logger.warning("Unknown input kind: %s", kind_str)
                continue
            existing = self._adapters.get(name)
            # Replace if the config OR the adapter kind changed (audit F12):
            # comparing config alone leaves the old adapter running after a
            # kind switch (e.g. webhook → sms_inbox with unchanged `{}`).
            if existing is not None and (
                existing.config != new_config or type(existing) is not wanted_cls
            ):
                logger.info("Adapter %s changed (config/kind) — restarting", name)
                try:
                    await existing.stop()
                except Exception:
                    logger.exception("stop %s before restart", name)
                del self._adapters[name]
                existing = None

            if existing is None:
                adapter = wanted_cls(
                    name=row.name,
                    config=new_config,
                    on_value=self._on_value_for(row.id),
                )
                await adapter.start()
                self._adapters[name] = adapter
                logger.info("Adapter %s started (kind=%s)", name, kind_str)

            # Push fresh topic filters
            filters = self._resolver.topic_filter_for_input("mqtt")
            await self._adapters[name].update_topics(filters)


def _var_to_mapping(v: Variable) -> VarMapping | None:
    """ORM Variable → resolver VarMapping. Returns None for sources
    a malformed source config (missing formula/cron/topic)."""
    cfg: dict[str, Any] = dict(v.config or {})
    src = v.source.value
    vtype = cfg.get("type", "number")

    if src == "mqtt":
        topic = cfg.get("topic")
        if not topic:
            logger.warning("Variable %s: mqtt source missing 'topic'", v.name)
            return None
        return VarMapping(
            name=v.name, source="mqtt", value_type=vtype,
            topic=topic, json_path=cfg.get("json_path"),
            stale_after_sec=effective_stale_after_sec("mqtt", cfg.get("stale_after_sec")),
            input_id=v.input_id,
        )
    if src == "aggregate":
        topics = cfg.get("topics", [])
        if not topics:
            logger.warning("Variable %s: aggregate source missing 'topics'", v.name)
            return None
        return VarMapping(
            name=v.name, source="aggregate", value_type=vtype,
            topics=list(topics), aggregate=cfg.get("aggregate", "sum"),
            json_path=cfg.get("json_path"),
            stale_after_sec=effective_stale_after_sec("aggregate", cfg.get("stale_after_sec")),
            input_id=v.input_id,
        )
    if src == "constant":
        return VarMapping(
            name=v.name, source="constant", value_type=vtype,
            constant_value=cfg.get("value"),
        )
    if src == "computed":
        formula = cfg.get("formula")
        if not formula:
            logger.warning("Variable %s: computed source missing 'formula'", v.name)
            return None
        return VarMapping(
            name=v.name, source="computed", value_type=vtype,
            formula=formula,
            stale_after_sec=effective_stale_after_sec("computed", cfg.get("stale_after_sec")),
        )
    if src == "schedule":
        cron = cfg.get("cron")
        if not cron:
            logger.warning("Variable %s: schedule source missing 'cron'", v.name)
            return None
        return VarMapping(
            # Schedule values pass through untyped (they're the operator's
            # literal 'value'); default True when none is given.
            name=v.name, source="schedule", value_type=cfg.get("type", "json"),
            cron=cron, constant_value=cfg.get("value", True),
        )
    return None


class VariableConfigError(ValueError):
    """A variable's config cannot be compiled into a runtime mapping/index —
    e.g. an mqtt ``topic`` given as a JSON object, which is unhashable and makes
    the hot reload raise (audit V09)."""


def dry_compile_variable(
    source: VariableSource,
    config: dict[str, Any],
    name: str = "_probe",
    input_id: int | None = None,
) -> None:
    """Raise :class:`VariableConfigError` if this config can't be compiled.

    The hot reload turns every enabled ``Variable`` row into a resolver mapping
    and rebuilds the topic index. A malformed config — most sharply an mqtt
    ``topic`` given as a JSON object or list, which is unhashable — makes that
    rebuild raise. Without this guard the row is committed first and the reload
    then 500s, leaving a persisted config that breaks *every* subsequent reload
    (audit V09). Create / update / import call this to reject such a config
    BEFORE committing, by compiling one transient mapping in a throwaway
    resolver — no DB access, no effect on the live index."""
    cfg = dict(config or {})
    # A computed variable's formula is an expression that the engine will
    # evaluate; reject one outside the language contract at write time, the same
    # way rule conditions are (audit A-01).
    if str(getattr(source, "value", source)) == "computed" and cfg.get("formula"):
        from .eval import ExpressionError, validate_expression
        try:
            validate_expression(cfg["formula"])
        except ExpressionError as e:
            raise VariableConfigError(f"formula: {e}") from e

    probe = Variable(
        name=name, source=source, config=cfg, input_id=input_id
    )
    mapping = _var_to_mapping(probe)
    if mapping is None:
        # A missing required field (topic/formula/cron) yields no mapping — the
        # variable is simply inert, not a reload hazard. Not our concern here.
        return
    try:
        VariableResolver(StateCache()).replace_mappings([mapping])
    except Exception as e:  # unhashable topic, non-iterable topic, etc.
        raise VariableConfigError(str(e)) from e


# ── Module singleton ──────────────────────────────────────────────


_manager: InputManager | None = None


def get_manager() -> InputManager:
    global _manager
    if _manager is None:
        _manager = InputManager()
    return _manager
