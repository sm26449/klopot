"""Rule engine — single asyncio task that ticks rules.

Each enabled rule has its own ``eval_interval_sec``. The engine
maintains a per-rule "next eval at" timestamp and wakes every
``base_tick_sec`` (default 1s) to find rules due for evaluation.

For each due rule:

  1. Build a context dict from the state cache, filtered by
     ``vars_extract`` (or all variables if empty)
  2. Eval ``condition_expr`` via ``app.core.eval``
  3. On match: increment ``rule_state.consecutive_match_count``
  4. When counter >= ``persist_n``: build FireEnvelope and call
     dispatcher.fire(); reset counter
  5. On non-match: reset counter (with 5-min flap window — TBD)
  6. On eval error: increment ``rules.consecutive_eval_errors``;
     warn at 5 consecutive; at ``eval_error_disable_threshold``
     (a missing input — a dotted variable absent from the cache — is
     recorded on the row but is neither an error nor a success)
     auto-disable the rule AND fire the built-in
     ``rule_auto_disabled`` alert (seeded by scripts/seed.py) so the
     operator is paged instead of finding out at the next audit

Hot reload: ``await engine.reload_rules()`` is called from the
manager whenever rules / templates / channels change.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from ..config import get_settings
from ..db import get_session, get_session_factory
from ..db.models import Incident, Rule, RuleState
from ..utils.time import utc_now
from . import dispatcher as dispatcher_module
from . import eval as eval_module
from . import gating as gating_module
from . import incidents
from .state_cache import StateCache, get_state_cache

logger = logging.getLogger(__name__)


@dataclass
class _RuleRuntime:
    """Per-rule runtime state held in memory.

    The persisted ``rule_state`` table mirrors this for restart
    survivability; we read it on startup, write it on every change.
    """

    rule: Rule
    next_eval_at: float = 0.0           # monotonic seconds
    consecutive_match_count: int = 0
    recovery_match_count: int = 0
    last_match_at: float | None = None
    consecutive_eval_errors: int = 0
    # Mirror of ``Rule.last_eval_error`` as last written, so a successful
    # eval clears it even when it was a not-counted "missing input" gap, and
    # unchanged errors are not rewritten every tick.
    last_eval_error: str | None = None
    # An ``eval_error`` activity event is open (a real error, not a
    # missing-input gap) and waits for its ``eval_recovered``.
    error_event_open: bool = False
    # The ``Rule.state_epoch`` this runtime was loaded under. Persisted
    # alongside the streak so a reset that happened after this runtime was
    # captured (audit B-06) cannot be undone by a late write from here.
    state_epoch: int = 0
    # True once a fire of this rule was suppressed by the template's
    # throttle and nothing has been delivered since. While set, further
    # matches inside the throttle window are dropped silently instead of
    # producing one "throttled" log row per eval (a value stuck in a
    # critical state produced 238 rows/day — 2026-09-09).
    throttled_since_dispatch: bool = False
    # The condition was definitively false since this rule last fired: the
    # next fire is a new occurrence, not the same one still matching. An
    # identical one inside the idempotency window is then logged as a
    # visible "duplicate" instead of vanishing into the earlier row (second
    # review, C13). Not persisted: after a restart it starts False.
    false_since_fire: bool = False


class RuleEngine:
    """Single instance per process. Owned by the input manager."""

    # last_evaluated_at writes are batched and flushed at this cadence
    # (audit H-2). 10s is fine-grained enough for operators to see
    # "is this rule actually running" but coarse enough that we don't
    # burn 26 commits/sec under full rule load.
    _TOUCH_FLUSH_SEC: float = 10.0

    def __init__(self, *, base_tick_sec: float = 1.0) -> None:
        self._base_tick = base_tick_sec
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()
        self._cache: StateCache = get_state_cache()
        self._rules: dict[int, _RuleRuntime] = {}
        # rule name → runtime (inhibition lookups) and rule name →
        # last truthy eval (monotonic). In-memory only: after a
        # restart, inhibition kicks in again on the inhibitor's first
        # truthy tick (brief non-inhibited window, documented).
        self._by_name: dict[str, _RuleRuntime] = {}
        self._last_truthy: dict[str, float] = {}
        self._reload_lock = asyncio.Lock()
        # Accumulates {rule_id: utc_now()} from _touch_evaluated_at;
        # flushed in batch by _flush_touches() every _TOUCH_FLUSH_SEC.
        self._pending_touches: dict[int, datetime] = {}
        self._last_flush: float = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        await self.reload_rules()
        self._task = asyncio.create_task(self._run(), name="rule-engine")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def is_alive(self) -> bool:
        """True if the ticker task started and is still running (audit F32)."""
        return self._task is not None and not self._task.done()

    async def reload_rules(self) -> None:
        """Re-read rules from DB and rebuild the in-memory schedule.

        Preserves ``consecutive_match_count`` for rules that still
        exist — both across in-process reloads (config tweak) AND
        across container restarts (cold start). The DB's rule_state
        row is the authoritative source on cold start.

        Without this (pre-audit H-1), a persist_n=6 rule already at
        count 5 would restart back to 0, requiring another 60s of
        sustained match before fire — sometimes never reaching it
        if the underlying condition flickers.
        """
        # Await session cleanup before evaluation can start. A deferred async
        # generator finalizer must not overlap the next state transaction.
        async with self._reload_lock, aclosing(get_session()) as sessions:
            async for s in sessions:
                rules = (
                    await s.execute(
                        select(Rule).where(Rule.enabled.is_(True))
                    )
                ).scalars().all()

                # Cold-start backstop: fetch persisted counters from
                # rule_state so a process restart doesn't lose them.
                rule_state_rows = (
                    await s.execute(select(RuleState))
                ).scalars().all()
                persisted: dict[int, RuleState] = {
                    rs.rule_id: rs for rs in rule_state_rows
                }

                # Preserve runtime state for rules we already track
                old = self._rules
                new: dict[int, _RuleRuntime] = {}
                now = _time.monotonic()
                for r in rules:
                    prev = old.get(r.id)
                    db_state = persisted.get(r.id)
                    if prev is not None:
                        # In-process reload — trust live counters, UNLESS
                        # the condition expression itself changed. A streak
                        # counted against the old expression says nothing
                        # about the new one, so a reconfigured rule starts
                        # fresh (audit A17) — including its inhibition
                        # marker, dropped below.
                        reconfigured = (
                            prev.rule.condition_expr != r.condition_expr
                            or prev.state_epoch != (r.state_epoch or 0)
                            or (
                                bool(prev.rule.incident_enabled or r.incident_enabled)
                                and incidents.lifecycle_config(prev.rule) != incidents.lifecycle_config(r)
                            )
                        )
                        cmc = 0 if reconfigured else prev.consecutive_match_count
                        rmc = 0 if reconfigured else prev.recovery_match_count
                        lma = None if reconfigured else prev.last_match_at
                        cee = prev.consecutive_eval_errors
                        lee = prev.last_eval_error
                        eeo = prev.error_event_open
                        if reconfigured:
                            self._last_truthy.pop(r.name, None)
                    else:
                        # Cold start — restore from rule_state row if
                        # any, fall back to Rule.consecutive_eval_errors
                        # for the eval-error counter (which lives on
                        # the Rule itself, not rule_state).
                        #
                        # Only trust the persisted streak if it was written
                        # under the rule's current state epoch. A row from an
                        # older epoch counted against a superseded expression
                        # (edited then restarted before a fresh persist, or a
                        # stale runtime's late write-back) and must start from
                        # zero (audit B-06).
                        if db_state and db_state.state_epoch == (r.state_epoch or 0):
                            cmc = db_state.consecutive_match_count
                            rmc = db_state.recovery_match_count
                        else:
                            cmc = 0
                            rmc = 0
                        # last_match_at lives in DB as wall-clock UTC
                        # but in-memory we use monotonic seconds.
                        # Approximate: if the row says "recent" (<24h
                        # ago), drop the field (we have no monotonic
                        # reference point — it's purely diagnostic).
                        # If we ever start GATING on last_match_at,
                        # change this to a (now - delta) reconstruction.
                        lma = None
                        cee = r.consecutive_eval_errors or 0
                        lee = r.last_eval_error
                        # Only real errors count; a missing-input gap
                        # leaves the counter at 0, so it opens no event.
                        eeo = cee > 0
                    new[r.id] = _RuleRuntime(
                        rule=r,
                        # Stagger initial evals so they don't all fire at t+0
                        next_eval_at=(prev.next_eval_at if prev else now + (r.id % 5)),
                        consecutive_match_count=cmc,
                        recovery_match_count=rmc,
                        last_match_at=lma,
                        consecutive_eval_errors=cee,
                        last_eval_error=lee,
                        error_event_open=eeo,
                        state_epoch=r.state_epoch or 0,
                    )
                self._rules = new
                self._by_name = {rt.rule.name: rt for rt in new.values()}
                # Drop truthy markers for rules that no longer exist
                # (renamed/deleted) so they can't inhibit forever.
                self._last_truthy = {
                    k: v for k, v in self._last_truthy.items()
                    if k in self._by_name
                }
                restored = sum(1 for r in rules
                               if old.get(r.id) is None and persisted.get(r.id))
                logger.info(
                    "Engine: %d rules loaded (restored persist counters "
                    "for %d cold-start rules from rule_state)",
                    len(new), restored,
                )
                break

    # ── Tick loop ─────────────────────────────────────────────────

    async def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                from ..metrics import ENGINE_LAST_TICK, ENGINE_TICK_DURATION

                with ENGINE_TICK_DURATION.time():
                    await self._tick()
                ENGINE_LAST_TICK.set(_time.time())
                # Flush accumulated last_evaluated_at writes every
                # _TOUCH_FLUSH_SEC (audit H-2). Cheap no-op when
                # _pending_touches is empty.
                now = _time.monotonic()
                if now - self._last_flush >= self._TOUCH_FLUSH_SEC:
                    self._last_flush = now
                    try:
                        await self._flush_touches()
                    except Exception:
                        logger.exception("flush touches failed")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("engine tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_evt.wait(), timeout=self._base_tick
                )
            except TimeoutError:
                pass
        # On graceful stop, flush any pending touches so we don't
        # lose the last 0-10s of bookkeeping.
        try:
            await self._flush_touches()
        except Exception:
            logger.exception("final flush failed")

    async def _tick(self) -> None:
        """One pass: evaluate every rule whose next_eval_at has passed."""
        now = _time.monotonic()
        # Guard against a runtime that was disabled mid-flight (e.g.
        # auto-disabled on the eval-error threshold) but not yet removed —
        # a disabled rule must never evaluate or fire (audit F10).
        due = [
            rt for rt in self._rules.values()
            if rt.rule.enabled and rt.next_eval_at <= now
        ]
        if not due:
            return
        for rt in due:
            # A reload earlier in this same tick (e.g. an admin disabling or
            # editing another due rule) can have swapped this runtime out or
            # dropped it; a disabled rule must never evaluate or fire (B-05).
            if not self._is_current(rt):
                continue
            try:
                await self._eval_rule(rt, now=now)
            except Exception:
                logger.exception("eval rule %s failed", rt.rule.name)
            rt.next_eval_at = now + rt.rule.eval_interval_sec

    def _is_current(self, rt: _RuleRuntime) -> bool:
        """True if ``rt`` is still THE live runtime for its rule and enabled.

        ``reload_rules`` swaps ``self._rules`` for freshly-built runtimes and
        drops disabled/deleted rules. A runtime captured earlier in a tick (in
        the ``due`` list) or before an ``await`` inside ``_eval_rule`` can be
        stale by the time we evaluate or fire it, so re-checking identity here
        stops a disabled/reconfigured rule from firing from stale work (B-05).
        """
        return self._rules.get(rt.rule.id) is rt and rt.rule.enabled

    def _remove_runtime(self, rt: _RuleRuntime) -> None:
        """Drop a rule runtime from every index atomically (audit F10).

        Used when a rule is auto-disabled so it is no longer runnable,
        name-resolvable, or usable as an inhibitor. A later explicit
        re-enable goes through ``reload`` which rebuilds the indexes.
        """
        self._rules.pop(rt.rule.id, None)
        self._by_name.pop(rt.rule.name, None)
        self._last_truthy.pop(rt.rule.name, None)

    async def _eval_rule(self, rt: _RuleRuntime, *, now: float) -> None:
        """Evaluate one rule against the current state cache."""
        ctx = self._build_context(rt.rule)

        settings = get_settings()
        from ..metrics import RULE_EVAL_DURATION_MS, RULE_EVAL_ERRORS_TOTAL

        eval_started = _time.monotonic()
        result = eval_module.evaluate(
            rt.rule.condition_expr,
            ctx,
            timezone=settings.tz,
            state_cache=self._cache,
        )
        recovery_matches = result.ok and not bool(result.value)
        active_incident = False
        if rt.rule.incident_enabled and recovery_matches:
            async with get_session_factory()() as session:
                active_incident = (await session.execute(select(Incident.id).where(
                    Incident.active_rule_id == rt.rule.id,
                ))).scalar_one_or_none() is not None
            if not self._is_current(rt):
                return
        if active_incident and rt.rule.recovery_expr:
            recovery = eval_module.evaluate(
                rt.rule.recovery_expr, ctx, timezone=settings.tz, state_cache=self._cache,
            )
            if not recovery.ok:
                # Unknown/missing data is never evidence of recovery. Reuse
                # the existing error accounting and consecutive-streak reset.
                result = recovery
            else:
                recovery_matches = bool(recovery.value)
        eval_ms = (_time.monotonic() - eval_started) * 1000
        RULE_EVAL_DURATION_MS.labels(rule_id=str(rt.rule.id)).observe(eval_ms)

        # Bookkeeping write — bumps last_evaluated_at every tick so
        # operators can see "is this rule actually running". Cheap
        # single-row UPDATE; eval intervals are ≥1s so worst case ~26
        # writes/sec at full load.
        await self._touch_evaluated_at(rt)

        if not result.ok and result.missing_input:
            # An input the rule needs is not in the cache: the rule has
            # nothing to say this tick. Shown on the row (last_eval_error)
            # so a typo is still visible, and NOT counted towards the early
            # warning / auto-disable — a gap is not an error. But it IS an
            # unknown transition, so the persist streak breaks: we can't
            # claim N consecutive confirmations across a tick with no data
            # (audit A17). The inhibition marker is left untouched — the
            # grace window covers a missed tick.
            await self._record_eval_error(rt, result.error, real=False)
            await self._reset_match_streak(rt)
            return
        if not result.ok:
            RULE_EVAL_ERRORS_TOTAL.labels(rule_id=str(rt.rule.id)).inc()
            rt.consecutive_eval_errors += 1
            await self._record_eval_error(rt, result.error or "unknown")
            if rt.consecutive_eval_errors == 5:
                # Rate-limited: only log once per early-warning point
                # (recovery is logged below). Include the actual error
                # reason so operators can distinguish 'NameError: sensor'
                # (= a whole var namespace went stale, e.g. a device asleep)
                # from a genuine syntax/coercion bug.
                logger.warning(
                    "Rule %s: 5 consecutive eval errors (early warning). "
                    "reason=%s",
                    rt.rule.name, result.error or "unknown",
                )
            disable_threshold = settings.eval_error_disable_threshold
            if (disable_threshold > 0
                    and rt.consecutive_eval_errors == disable_threshold):
                # Closes the silent-failure class that bit us twice
                # (2026-05-15 sunset namespace drop, 2026-05-24 thermal v5
                # cutover). A rule that can't evaluate for N ticks is more
                # dangerous than a disabled rule — at least the latter
                # shows up red on the admin Rules tab.
                logger.error(
                    "Rule %s: AUTO-DISABLED after %d consecutive eval "
                    "errors. reason=%s. Re-enable via PATCH /v1/rules/%d "
                    "after fixing the underlying binding.",
                    rt.rule.name, disable_threshold,
                    result.error or "unknown", rt.rule.id,
                )
                # Capture primitives BEFORE the commit below — the
                # commit expires the ORM instance and any later lazy
                # attribute load would raise MissingGreenlet.
                rule_id = rt.rule.id
                rule_name = rt.rule.name
                tpl_type = rt.rule.template_type
                rt.rule.enabled = False
                async for s in get_session():
                    await s.execute(
                        update(Rule)
                        .where(Rule.id == rule_id)
                        .values(enabled=False)
                    )
                    await s.commit()
                    break
                from .activity import record_event
                record_event(source_kind="rule", source_id=rule_id, source_name=rule_name, event="auto_disabled",
                             detail=f"after {disable_threshold} evaluation errors: {result.error or 'unknown'}")
                await self._fire_meta_auto_disabled(
                    rule_id=rule_id,
                    rule_name=rule_name,
                    template_type=tpl_type,
                    error=result.error or "unknown",
                    threshold=disable_threshold,
                )
                # Remove the runtime from every index so it can't be
                # evaluated, re-fired or act as an inhibitor again until an
                # explicit re-enable/reload re-adds it (audit F10).
                self._remove_runtime(rt)
                return
            # An error is an unknown transition too — break the persist
            # streak so a flapping expression can't accumulate matches
            # across failed ticks (audit A17). Inhibition marker untouched.
            await self._reset_match_streak(rt)
            return

        # Successful eval — reset the error counter and clear the last error,
        # including a not-counted "missing input" gap that has since healed.
        if rt.consecutive_eval_errors or rt.last_eval_error:
            if rt.consecutive_eval_errors >= 5:
                logger.info(
                    "Rule %s: recovered after %d consecutive eval errors",
                    rt.rule.name, rt.consecutive_eval_errors,
                )
            rt.consecutive_eval_errors = 0
            await self._record_eval_error(rt, None)

        if rt.rule.incident_enabled:
            await self._eval_incident_rule(rt, bool(result.value), recovery_matches, ctx, now, active_incident)
            return

        truthy = bool(result.value)
        if not truthy:
            # Definitive false transition (audit A17): the condition is
            # genuinely not met this tick — break the persist streak AND
            # drop the inhibition marker immediately. The grace window in
            # _active_inhibitor exists to tolerate *missed* ticks, not an
            # explicit false, so a rule that just evaluated false must stop
            # inhibiting its dependents right away.
            await self._reset_match_streak(rt)
            self._last_truthy.pop(rt.rule.name, None)
            rt.false_since_fire = True
            return

        # Match!
        self._last_truthy[rt.rule.name] = now  # inhibition marker
        rt.consecutive_match_count += 1
        rt.last_match_at = now
        await self._persist_state(rt)

        if rt.consecutive_match_count >= rt.rule.persist_n:
            # Re-check liveness at the fire boundary: _eval_rule has awaited
            # (eval, touch, persist) since the tick's guard, and a reload
            # during those awaits can have disabled or replaced this rule.
            # Never commit fire intent for a runtime that is no longer the
            # live one for its rule (audit B-05).
            if not self._is_current(rt):
                return
            if rt.throttled_since_dispatch and await self._template_throttled(rt.rule.template_type):
                # Same condition, still inside min_repeat, already logged
                # once as throttled: a re-fire carries no information.
                rt.consecutive_match_count = 0
                await self._persist_state(rt)
                return
            # Build envelope and dispatch
            envelope = dispatcher_module.FireEnvelope(
                type=rt.rule.template_type,
                context=self._build_dispatch_context(rt.rule, ctx),
                test=False,
                source="engine",
                rule_id=rt.rule.id,
                inhibited_by_active=self._active_inhibitor(rt, now),
                reoccurrence=rt.false_since_fire,
            )
            rt.false_since_fire = False
            try:
                async for s in get_session():
                    res = await dispatcher_module.fire(envelope, s)
                    reason = getattr(res, "suppressed_reason", None)
                    reason = getattr(reason, "value", reason)
                    rt.throttled_since_dispatch = (
                        not getattr(res, "dispatched", False) and reason == "throttled"
                    )
                    # Audit #104 (2026-05-17, v1.3.4): bump last_fired_at
                    # on every successful match (persist_n reached) —
                    # NOT only when the dispatch landed. Previously a
                    # rule that fired constantly but was throttled
                    # showed a stale last_fired_at on the admin Rules
                    # tab and looked dormant; operators couldn't tell
                    # the difference between "this rule never fires"
                    # and "this rule fires constantly but is gated".
                    await s.execute(
                        update(Rule)
                        .where(Rule.id == rt.rule.id)
                        .values(last_fired_at=utc_now())
                    )
                    # fire_count_lifetime — the canonical "did anyone get
                    # notified" counter — is accounted inside dispatcher.fire
                    # now, through an idempotent CAS (audit V08), so a first
                    # success that only lands on a retry is still counted
                    # exactly once. This commit persists that accounting
                    # together with last_fired_at.
                    await s.commit()
                    break
            except Exception:
                logger.exception("dispatch from rule %s", rt.rule.name)
            # Reset persist counter regardless of dispatch outcome —
            # the gate (throttle) decides whether subsequent matches
            # fire too soon.
            rt.consecutive_match_count = 0
            await self._persist_state(rt)

    async def _eval_incident_rule(
        self, rt: _RuleRuntime, firing: bool, recovery: bool,
        context: dict[str, Any], now: float, active: bool,
    ) -> None:
        if not self._is_current(rt):
            return
        if firing:
            self._last_truthy[rt.rule.name] = now
            rt.last_match_at = now
            rt.recovery_match_count = 0
            rt.consecutive_match_count += 1
            if rt.consecutive_match_count >= rt.rule.persist_n:
                async for session in get_session():
                    await incidents.fire_rule(
                        session, rt.rule, rt.state_epoch,
                        self._build_dispatch_context(rt.rule, context),
                        self._active_inhibitor(rt, now),
                    )
                    await session.commit()
                    break
                rt.consecutive_match_count = 0
            await self._persist_state(rt)
            return

        rt.consecutive_match_count = 0
        if not active:
            rt.recovery_match_count = 0
            self._last_truthy.pop(rt.rule.name, None)
        else:
            # Hysteresis keeps the incident active between its two thresholds.
            self._last_truthy[rt.rule.name] = now
            rt.recovery_match_count = rt.recovery_match_count + 1 if recovery else 0
            if rt.recovery_match_count >= rt.rule.recovery_persist_n:
                async for session in get_session():
                    await incidents.recover_rule(
                        session, rt.rule, rt.state_epoch,
                        self._build_dispatch_context(rt.rule, context),
                    )
                    await session.commit()
                    break
                rt.recovery_match_count = 0
                self._last_truthy.pop(rt.rule.name, None)
        await self._persist_state(rt)

    async def _template_throttled(self, template_type: str) -> bool:
        """True while the template's min_repeat window is still open."""
        try:
            async for s in get_session():
                template = await dispatcher_module._load_template(s, template_type)
                if template is None:
                    return False
                return await gating_module._is_throttled(template, s)
        except Exception:
            logger.exception("throttle pre-check for %s", template_type)
        return False

    async def _reset_match_streak(self, rt: _RuleRuntime) -> None:
        """Break the consecutive-match streak (audit A17).

        Called on every non-truthy transition — false, missing input,
        eval error — so ``persist_n`` only fires on N genuinely
        consecutive truthy evals. No-op (and no DB write) when the streak
        is already zero.
        """
        if rt.consecutive_match_count or rt.recovery_match_count:
            rt.consecutive_match_count = 0
            rt.recovery_match_count = 0
            await self._persist_state(rt)

    def _active_inhibitor(self, rt: _RuleRuntime, now: float) -> str | None:
        """Return the name of the first ACTIVE inhibitor of this rule.

        Alertmanager-style storm correlation: a rule listing
        ``inhibited_by: ["mqtt_broker_down_v1"]`` stays quiet while
        that rule is active, so one root cause pages once instead of
        cascading through every dependent rule.

        "Active" = the inhibitor evaluated truthy within its own grace
        window (2 × its eval interval + 5s — one missed tick doesn't
        drop the inhibition). Unknown/disabled inhibitors and
        self-references are ignored (fail-open: better a duplicate
        page than a silently suppressed real alert).
        """
        for name in rt.rule.inhibited_by or []:
            if name == rt.rule.name:
                continue
            inhibitor = self._by_name.get(name)
            if inhibitor is None:
                continue
            t = self._last_truthy.get(name)
            if t is None:
                continue
            grace = 2 * inhibitor.rule.eval_interval_sec + 5
            if (now - t) <= grace:
                return name
        return None

    async def _fire_meta_auto_disabled(
        self,
        *,
        rule_id: int,
        rule_name: str,
        template_type: str,
        error: str,
        threshold: int,
    ) -> None:
        """Page the operator when a rule auto-disables.

        A rule dying silently is exactly the failure class this engine
        exists to prevent — so the engine alerts about itself through
        the same dispatch pipeline (template ``rule_auto_disabled``,
        seeded by scripts/seed.py; if it was deleted, the dispatcher
        still records an ``unknown_type`` audit row). Takes primitives,
        not the ORM object (expired after the disable commit). Any
        failure here must never break the eval loop.
        """
        envelope = dispatcher_module.FireEnvelope(
            type="rule_auto_disabled",
            context={
                "rule_name": rule_name,
                "rule_id": rule_id,
                "template_type": template_type,
                "error": error,
                "threshold": threshold,
            },
            test=False,
            source="engine-meta",
        )
        try:
            async for s in get_session():
                await dispatcher_module.fire(envelope, s)
                await s.commit()
                break
        except Exception:
            logger.exception(
                "meta-alert rule_auto_disabled failed for rule %s", rule_name
            )

    # ── Helpers ───────────────────────────────────────────────────

    def _build_context(self, rule: Rule) -> dict[str, Any]:
        """Snapshot the state cache filtered by ``vars_extract``.

        Empty list = all variables (common during early development).
        Specific list = only those names (preferred for production
        rules — explicit dependencies, clear telemetry).

        Stale-variable handling (audit H-4): variables whose age
        exceeds their declared ``stale_after_sec`` are DROPPED from
        the context. The rule expression then surfaces them as
        ``NameNotDefined`` → eval returns ok=False → no match. This
        is intentionally loud — better than silently firing on
        phantom data when the MQTT broker drops mid-day.

        Rules that need graceful degradation can opt in by using
        the ``var_age("name")`` function in their condition, which
        reads ts from the state_cache directly (bypassing context).
        """
        snap = self._cache.snapshot()
        if rule.vars_extract:
            wanted = set(rule.vars_extract)
            items = ((k, v) for k, v in snap.items() if k in wanted)
        else:
            items = snap.items()
        ctx: dict[str, Any] = {}
        dropped: list[str] = []
        for k, v in items:
            if v.is_stale():
                dropped.append(k)
                continue
            ctx[k] = v.value
        if dropped:
            logger.debug(
                "Rule %s context: dropped %d stale var(s): %s",
                rule.name, len(dropped), ",".join(dropped),
            )
        return ctx

    def _build_dispatch_context(self, rule: Rule, eval_ctx: dict[str, Any]) -> dict[str, Any]:
        """Context passed to the template renderer. Same as eval_ctx
        for now; later we may add ``_meta`` fields like ``rule_id``,
        ``fired_at``, ``state_age_sec``."""
        return dict(eval_ctx)

    async def _persist_state(self, rt: _RuleRuntime) -> None:
        """Mirror in-memory runtime to ``rule_state``."""
        async for s in get_session():
            existing = (
                await s.execute(
                    select(RuleState).where(RuleState.rule_id == rt.rule.id)
                )
            ).scalar_one_or_none()
            if existing is None:
                s.add(RuleState(
                    rule_id=rt.rule.id,
                    consecutive_match_count=rt.consecutive_match_count,
                    recovery_match_count=rt.recovery_match_count,
                    last_match_at=utc_now() if rt.last_match_at else None,
                    state_epoch=rt.state_epoch,
                ))
            else:
                existing.consecutive_match_count = rt.consecutive_match_count
                existing.recovery_match_count = rt.recovery_match_count
                # Stamp the epoch this runtime belongs to. A stale runtime
                # (captured before a reconfig reset) writes the OLD epoch here,
                # which cold start then discards — so its late write-back
                # cannot resurrect the superseded streak (audit B-06).
                existing.state_epoch = rt.state_epoch
                if rt.last_match_at is not None:
                    existing.last_match_at = utc_now()
            await s.commit()
            break

    async def _record_eval_error(self, rt: _RuleRuntime, error: str | None, *, real: bool = True) -> None:
        """Record eval error count + last error message on the Rule row.

        ``last_evaluated_at`` is updated by ``_touch_evaluated_at`` on
        every eval, so we don't bump it here. Skips the write when neither
        the message nor the counter changed (a "missing input" gap repeats
        the same text every tick). ``real=False`` is a missing-input gap:
        stored on the row but never an activity event (a restart would
        otherwise log an error/recovered pair for every rule)."""
        persisted = (rt.rule.consecutive_eval_errors or 0, rt.last_eval_error)
        if persisted == (rt.consecutive_eval_errors, error):
            return
        # Activity log: only the transitions OK → error and error → OK, and
        # only for real errors.
        want_open = bool(error) and real
        if want_open != rt.error_event_open:
            from .activity import record_event
            record_event(source_kind="rule", source_id=rt.rule.id, source_name=rt.rule.name,
                         event="eval_error" if want_open else "eval_recovered", detail=error if want_open else None)
            rt.error_event_open = want_open
        rt.last_eval_error = error
        rt.rule.consecutive_eval_errors = rt.consecutive_eval_errors
        async for s in get_session():
            await s.execute(
                update(Rule)
                .where(Rule.id == rt.rule.id)
                .values(
                    consecutive_eval_errors=rt.consecutive_eval_errors,
                    last_eval_error=error,
                )
            )
            await s.commit()
            break

    async def _touch_evaluated_at(self, rt: _RuleRuntime) -> None:
        """Stamp ``last_evaluated_at`` so operators can see the engine is
        actually ticking each rule.

        Audit H-2 (2026-05-14): previously did a single-row UPDATE +
        commit per call. With 26 enabled rules ticking every ~1-10s,
        worst case was ~26 commits/sec just for bookkeeping — heavy
        binlog churn for no real value. Now accumulates in-memory
        and flushes in a batch every ``_TOUCH_FLUSH_SEC`` seconds
        (default 10s) via ``_flush_touches()`` called from the tick
        loop. Net result: 1 batched commit per 10s regardless of
        rule count.
        """
        self._pending_touches[rt.rule.id] = utc_now()

    async def _flush_touches(self) -> None:
        """Persist accumulated last_evaluated_at stamps in one trip."""
        if not self._pending_touches:
            return
        # Snapshot + clear so concurrent _touch calls during the
        # flush don't get lost or double-written.
        to_write = self._pending_touches
        self._pending_touches = {}
        async for s in get_session():
            for rule_id, ts in to_write.items():
                await s.execute(
                    update(Rule).where(Rule.id == rule_id)
                    .values(last_evaluated_at=ts)
                )
            await s.commit()
            break


# ── Module singleton ─────────────────────────────────────────────


_engine: RuleEngine | None = None


def get_engine() -> RuleEngine:
    global _engine
    if _engine is None:
        _engine = RuleEngine()
    return _engine
