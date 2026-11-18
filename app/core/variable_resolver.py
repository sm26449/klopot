"""Map raw input messages to typed variable values in the cache.

Responsibilities:

1. Build a topic→variables index from the ``variables`` DB rows.
2. On each (topic, payload) callback from an input adapter, look up
   matching variables, extract the value (JSONPath / raw / aggregate
   member), coerce to the declared type, write to the state cache.
3. Expose the index summary so input adapters can build their
   filter sets (S3 MQTT uses this).

Variable sources:
- ``mqtt`` — direct topic→value with optional ``json_path``
- ``aggregate`` — sum/avg/max/min over members of a topic group
- ``constant`` — static, written once at start
- ``computed`` — formula over other variables, recomputed on dependency
  change (audit A15)
- ``schedule`` — cron-driven slot value, latched by the manager's clock
  tick (audit A15)
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..config import get_settings
from .state_cache import StateCache

logger = logging.getLogger(__name__)


@dataclass
class VarMapping:
    """One variable's resolution rule."""

    name: str
    source: str            # "mqtt" / "aggregate" / "computed" / "constant" / "schedule"
    value_type: str        # "number" / "bool" / "string" / "json"
    # Source-specific:
    topic: str | None = None             # mqtt single topic
    json_path: str | None = None         # dot-path within JSON payload
    topics: list[str] = field(default_factory=list)   # aggregate members
    aggregate: str | None = None          # sum/avg/max/min
    formula: str | None = None            # computed: expression over vars
    cron: str | None = None               # schedule: cron for the slot value
    constant_value: Any = None            # constant value / schedule slot value
    stale_after_sec: int | None = None
    # Which declared input this variable is bound to (audit A32). A
    # message only updates the variable when it came from this input;
    # None means "unbound" — any input delivering the topic may update it.
    input_id: int | None = None


class VariableResolver:
    """Topic → variable lookup + value extraction."""

    def __init__(self, cache: StateCache) -> None:
        self._cache = cache
        self._mappings: dict[str, VarMapping] = {}
        self._exact_index: dict[str, list[VarMapping]] = {}
        self._wildcard_index: dict[str, list[VarMapping]] = {}
        # For aggregate variables: per-name → {member_topic: (value, ts)}
        self._agg_buffers: dict[str, dict[str, Any]] = {}
        # Aggregates whose member buffer is at the budget and refusing new
        # members (audit D1-01). While present, the aggregate's output is held
        # invalid (None) rather than a falsely-complete sum.
        self._agg_overflow: set[str] = set()
        # Per-aggregate member budget (audit D1-01); 0 = unbounded. Attribute
        # so tests can set a small cap.
        self._max_agg_members: int = get_settings().max_aggregate_members
        # For schedule variables: per-name → last wall-clock we evaluated
        # the cron against (so we can detect a fire inside the gap).
        self._sched_last: dict[str, datetime] = {}

    # ── Configuration ─────────────────────────────────────────────

    def replace_mappings(self, mappings: list[VarMapping]) -> set[str]:
        """Atomically swap the index. Called by manager on hot reload.

        Returns the set of variable names whose cached values were
        invalidated by this swap (audit A06): a variable that was
        removed (deleted/disabled → dropped from the enabled set) or
        rebound (its ``VarMapping`` changed — a new topic/source/
        constant value/etc.) must not keep serving its stale cached
        value to the rule engine and ``/v1/state``.

        Only names this resolver previously managed are considered, so
        cache entries written by other producers (e.g. the channel
        breaker's ``channel.*`` ``internal`` variables) are never
        touched. The diff + ``cache.clear`` run synchronously with the
        index swap — no ``await`` in between — so the invalidation is
        atomic with the reload from the event loop's point of view.
        Constants that survive are re-written immediately afterwards by
        the manager via ``seed_constants``.
        """
        old = self._mappings
        new = {m.name: m for m in mappings}
        # A name is invalidated when it disappears (delete/disable) or
        # when its binding changed (rebind). VarMapping is a dataclass,
        # so ``!=`` compares every field (source, topic, json_path,
        # topics, aggregate, constant_value, value_type, stale).
        invalidated = {
            name for name, old_m in old.items()
            if new.get(name) != old_m
        }
        if invalidated:
            self._cache.clear(only=invalidated)

        self._mappings = new
        # Rebuild indexes
        exact: dict[str, list[VarMapping]] = {}
        wildcard: dict[str, list[VarMapping]] = {}
        for m in mappings:
            for t in self._topics_for(m):
                bucket = wildcard if ("+" in t or "#" in t) else exact
                bucket.setdefault(t, []).append(m)
        self._exact_index = exact
        self._wildcard_index = wildcard

        # Retain aggregate member history across the swap instead of wiping
        # it unconditionally (audit B-03). An aggregate whose binding is
        # unchanged keeps its whole buffer, so a reload triggered by an
        # unrelated edit can't silently drop a quiet member that won't
        # republish for a while (retained-only MQTT sources may not replay).
        # An aggregate whose binding changed (or a brand-new one) keeps only
        # the members whose topic is still part of its membership — old
        # members that no longer apply are forgotten.
        old_buffers = self._agg_buffers
        new_buffers: dict[str, dict[str, Any]] = {}
        for m in mappings:
            if m.source != "aggregate":
                continue
            prev = old_buffers.get(m.name, {})
            if m.name not in invalidated:
                new_buffers[m.name] = prev
            else:
                member_topics = set(self._topics_for(m))
                new_buffers[m.name] = {
                    topic: val for topic, val in prev.items()
                    if topic in member_topics
                }
        self._agg_buffers = new_buffers

        logger.info(
            "Resolver: %d variables, %d exact topics, %d wildcards, "
            "%d invalidated",
            len(mappings), len(exact), len(wildcard), len(invalidated),
        )
        return invalidated

    def topic_filter_for_input(self, input_kind: str = "mqtt") -> dict[str, set[str]]:
        """Return the topic filter sets the input adapter should use.

        For MQTT, this gives ``{"exact": {...}, "wildcard": {...}}``
        ready to pass to ``MQTTSubscriber.update_topics``.
        """
        if input_kind != "mqtt":
            return {"exact": set(), "wildcard": set()}
        return {
            "exact": set(self._exact_index.keys()),
            "wildcard": set(self._wildcard_index.keys()),
        }

    def known_var_names(self) -> set[str]:
        return set(self._mappings.keys())

    # ── Constants — write once at start ───────────────────────────

    async def seed_constants(self) -> None:
        """Write all ``constant`` variables into the cache.

        Called by manager once after replace_mappings. Constants never
        go stale — leave ``stale_after_sec=None``."""
        for m in self._mappings.values():
            if m.source == "constant":
                await self._cache.set(
                    m.name, m.constant_value,
                    source_topic=None, source_kind="constant",
                    stale_after_sec=None,
                )

    # ── Computed variables — formula over other variables (S4) ────

    async def recompute_computed(self) -> None:
        """Recompute all ``computed`` variables from the current cache.

        Evaluates each variable's formula (expression language) over the
        live variable values. Runs to a fixpoint so a chain (``c = a + b``;
        ``d = c * 2``) converges; the iteration is bounded by the number of
        computed variables so a cyclic formula can't spin forever.

        Freshness semantics (audit F07/F08):

        * A **stale** dependency is treated as absent, so a computed result
          is never refreshed from expired evidence (F07). The fixpoint is
          resolved in a local working set, so a chain converges without
          writing intermediate tombstones to the shared cache.
        * A computed variable that **cannot** resolve this pass (missing or
          stale dependency, or an eval error) has its previous output
          invalidated to ``None`` instead of being left ``fresh forever``
          (F07) — a value with no live evidence behind it must not keep
          matching rules.
        * A computed variable that re-evaluates to the **same** value has
          its freshness timestamp refreshed (F08), so a continuously-fresh
          dependency keeps the result alive even when it never changes.
        * A computed result's evidence deadline is bounded by its actual
          dependencies (audit B-04): it expires no later than the soonest
          dependency it was built from, so a long-TTL computed cannot keep
          presenting a value derived from a short-TTL input that has already
          expired. This holds transitively down a chain.
        """
        from .engine import settings_evaluator
        from .eval import evaluate as _evaluate
        from .eval import referenced_names as _referenced_names

        computed = [m for m in self._mappings.values() if m.source == "computed"]
        if not computed:
            return
        # The install's timezone and place, like rules (a formula's
        # hour_now() was UTC).
        evaluator = settings_evaluator(self._cache)

        now = time.monotonic()
        snap = self._cache.snapshot()
        computed_names = {m.name for m in computed}
        # F07: exclude stale dependencies — an expired input must not feed a
        # computed result and present it as current.
        #
        # V07: also exclude every computed node's *own* previous output from the
        # base. A descendant must derive its inputs from this pass's freshly
        # recomputed values (``results``), never from a stale intermediate left
        # in the snapshot — otherwise invalidating ``b`` (because ``a`` went
        # away) still lets ``c = b*2`` read the old ``b`` from the snapshot and
        # keep a value with no live evidence behind it. With computed nodes kept
        # out of the base, a node whose computed dependency didn't resolve this
        # pass evaluates against an undefined name, fails, and is invalidated —
        # so unavailable/error propagates transitively down the chain. (The
        # graph is treated as a DAG; a self-referential/cyclic formula simply
        # never resolves and is invalidated rather than reusing its old value.)
        base_ctx = {
            name: s.value
            for name, s in snap.items()
            if not s.is_stale(now) and name not in computed_names
        }
        # B-04: each non-stale base variable's own evidence deadline, so a
        # computed result can inherit the soonest one of its dependencies.
        base_exp = {
            name: s.expires_at
            for name, s in snap.items()
            if not s.is_stale(now) and name not in computed_names
        }

        # Resolve the fixpoint locally (name -> coerced value) so a dependency
        # chain converges without touching the cache mid-iteration. Each outer
        # pass rebuilds ``ctx`` from the latest ``results``, so a chain resolves
        # one level deeper per pass (topological order), bounded below.
        results: dict[str, Any] = {}
        # B-04: the evidence deadline computed alongside each result, so a
        # dependent inherits its parents' deadlines transitively.
        result_exp: dict[str, float | None] = {}
        for _ in range(len(computed) + 1):
            changed = False
            ctx = {**base_ctx, **results}
            for m in computed:
                res = _evaluate(m.formula or "", ctx, evaluator=evaluator)
                if not res.ok:
                    continue
                new_val = _coerce(res.value, m.value_type)
                # Bound this result's freshness by its own TTL and by the
                # soonest deadline among the dependencies it actually reads
                # (audit B-04). A dependency with no deadline (constant /
                # schedule) doesn't constrain it; a missing one can't occur
                # here because an unresolved name fails the eval above.
                own = now + m.stale_after_sec if m.stale_after_sec is not None else None
                dep_exps = [
                    result_exp[d] if d in result_exp else base_exp[d]
                    for d in _referenced_names(m.formula or "")
                    if d in result_exp or d in base_exp
                ]
                result_exp[m.name] = _min_deadline(own, *dep_exps)
                if m.name not in results or results[m.name] != new_val:
                    results[m.name] = new_val
                    changed = True
            if not changed:
                break

        # Apply the converged results to the shared cache.
        for m in computed:
            cur = self._cache.get(m.name)
            if m.name in results:
                new_val = results[m.name]
                exp = result_exp.get(m.name)
                if cur is None or cur.value != new_val:
                    await self._cache.set(
                        m.name, new_val, source_topic=None,
                        source_kind="computed", stale_after_sec=m.stale_after_sec,
                        expires_at=exp,
                    )
                else:
                    # F08: unchanged but dependencies are fresh — restart the
                    # staleness clock (to the recomputed evidence deadline,
                    # audit B-04) without a redundant fanout.
                    self._cache.touch(m.name, expires_at=exp)
            elif cur is not None and cur.value is not None:
                # F07: no live evidence this pass — invalidate the stale output.
                await self._cache.set(
                    m.name, None, source_topic=None,
                    source_kind="computed", stale_after_sec=m.stale_after_sec,
                )

    async def recompute_aggregates(self, only: set[str] | None = None) -> None:
        """Recompute aggregates from their retained buffers.

        Called by the manager after a reload so an aggregate whose binding
        changed (its output was invalidated by the swap) is republished from
        its still-applicable members immediately, instead of reading ``None``
        until the next member message happens to arrive (audit B-03). With
        ``only`` given, limits the work to those names.
        """
        now = time.monotonic()
        for m in self._mappings.values():
            if m.source != "aggregate":
                continue
            if only is not None and m.name not in only:
                continue
            await self._recompute_aggregate(
                m, now, source_topic=None, source_kind="aggregate",
            )

    async def sweep(self, now: float | None = None) -> None:
        """Clock-driven freshness pass (audit B-04).

        Recompute every aggregate so an expired member drops out of the
        output and the output's deadline tracks the earliest remaining
        member, then recompute computed variables so a result whose evidence
        expired is invalidated — all without waiting for the next inbound
        message. Idempotent: aggregates write only when the value or its
        deadline actually moved, and an unchanged computed is merely re-timed
        against its live dependencies. Driven by the manager's clock tick.
        """
        now = time.monotonic() if now is None else now
        for m in self._mappings.values():
            if m.source == "aggregate":
                await self._recompute_aggregate(
                    m, now, source_topic=None, source_kind="aggregate",
                    force=False,
                )
        await self.recompute_computed()

    # ── Schedule variables — cron-driven slot value (S7) ──────────

    async def evaluate_schedules(self, now: datetime) -> None:
        """Set each ``schedule`` variable to its slot value when its cron
        fires inside the window since the last evaluation.

        The value latches: it stays in the cache until the next fire (a
        time-of-day slot value). The first call per variable only records
        a baseline so a restart doesn't replay a past fire."""
        from croniter import croniter

        touched = False
        for m in self._mappings.values():
            if m.source != "schedule" or not m.cron:
                continue
            last = self._sched_last.get(m.name)
            self._sched_last[m.name] = now
            if last is None or now <= last:
                continue
            nxt = croniter(m.cron, last).get_next(datetime)
            if last < nxt <= now:
                await self._cache.set(
                    m.name, m.constant_value, source_topic=None,
                    source_kind="schedule", stale_after_sec=None,
                )
                touched = True

        # A schedule fire can feed a computed variable; propagate it the same
        # way an inbound message does, instead of waiting for the next message
        # to happen to trigger recomputation (audit F09).
        if touched:
            await self.recompute_computed()

    # ── Inbound message handler — passed as on_value to adapters ──

    async def handle_inbound(
        self, topic: str, payload: Any, source_kind: str,
        input_id: int | None = None,
    ) -> None:
        """Called by input adapters per received message.

        ``input_id`` identifies the input that delivered this message
        (bound per-adapter by the manager). A variable is updated only
        when it is bound to this input, or is unbound (audit A32: two
        inputs sharing a topic must not cross-update each other's
        variables).

        Propagates ``stale_after_sec`` from the VarMapping into the
        state cache so the rule engine can gate eval on freshness
        (audit H-4). After applying the direct update, recomputes any
        ``computed`` variables that depend on it (audit A15)."""
        touched = False
        for m in self._lookup(topic, input_id):
            if m.source == "mqtt":
                value = _extract_typed(payload, m.json_path, m.value_type)
                if value is _MISSING:
                    continue
                # value may be None here (JSON null) — propagate it so
                # downstream consumers see the invalidation.
                await self._cache.set(
                    m.name, value, source_topic=topic, source_kind=source_kind,
                    stale_after_sec=m.stale_after_sec,
                )
                touched = True
            elif m.source == "aggregate":
                value = _extract_typed(payload, m.json_path, m.value_type)
                if value is _MISSING:
                    # The topic matched but the JSON path didn't resolve in
                    # this payload — ambiguous, so leave the member as-is.
                    continue
                buf = self._agg_buffers.setdefault(m.name, {})
                now = time.monotonic()
                self._evict_stale_members(m, buf, now)
                if value is None:
                    # JSON null explicitly invalidates this member's
                    # contribution (audit A16): drop it so a stale value
                    # can't keep inflating the aggregate.
                    buf.pop(topic, None)
                    self._agg_overflow.discard(m.name)
                elif (
                    topic not in buf
                    and self._max_agg_members
                    and len(buf) >= self._max_agg_members
                ):
                    # Member budget reached (audit D1-01). Refuse the new
                    # member and INVALIDATE the output rather than silently
                    # trimming while presenting a complete sum. Recovers once
                    # eviction frees a slot. Observable via log + health.
                    if m.name not in self._agg_overflow:
                        self._agg_overflow.add(m.name)
                        logger.warning(
                            "aggregate %s hit member budget %d; refusing new "
                            "member %s and invalidating output",
                            m.name, self._max_agg_members, topic,
                        )
                    await self._cache.set(
                        m.name, None, source_topic=topic, source_kind=source_kind,
                        stale_after_sec=m.stale_after_sec,
                    )
                    touched = True
                    continue
                else:
                    # Store the value WITH its arrival time so stale members
                    # can be excluded on recompute (audit A16).
                    buf[topic] = (value, now)
                    self._agg_overflow.discard(m.name)
                await self._recompute_aggregate(
                    m, now, source_topic=topic, source_kind=source_kind,
                )
                touched = True

        # A direct update may feed a computed variable (audit A15).
        if touched:
            await self.recompute_computed()

    # ── Internals ─────────────────────────────────────────────────

    async def _recompute_aggregate(
        self, m: VarMapping, now: float, *, source_topic: str | None,
        source_kind: str, force: bool = True,
    ) -> None:
        """Recompute an aggregate from its buffered members (audit A16).

        Only members that are still *fresh* contribute: when the mapping
        declares ``stale_after_sec`` a member whose last value is older
        than that window is excluded, so a member that stopped publishing
        can't keep inflating the sum while being presented as current.
        With no ``stale_after_sec`` policy there is no time-based staleness
        and every buffered member contributes (minus any null-invalidated
        one). An empty fresh set writes ``None`` — an explicit tombstone —
        rather than leaving the last good aggregate standing.

        The output's evidence deadline is the *earliest* contributing
        member's expiry (``min(member_ts) + stale``), not ``now + stale``
        (audit B-04): the aggregate must go stale when its soonest member
        does, instead of looking fresh because the recompute itself is
        recent. With ``force=False`` (the clock-driven sweep) the write is
        skipped when neither the value nor the deadline moved, so an
        idle sweep doesn't fan out to subscribers needlessly.
        """
        buf = self._agg_buffers.get(m.name, {})
        stale = m.stale_after_sec
        # D1-01: delete expired members from storage, not just from the sum, so
        # a wildcard aggregate under topic churn plateaus in memory and CPU
        # instead of rescanning every historical topic forever.
        self._evict_stale_members(m, buf, now)
        if m.name in self._agg_overflow:
            if self._max_agg_members and len(buf) >= self._max_agg_members:
                # Still over budget — hold the output invalid rather than
                # recompute a partial sum that looks complete (audit D1-01).
                cur = self._cache.get(m.name)
                if cur is None or cur.value is not None:
                    await self._cache.set(
                        m.name, None, source_topic=source_topic,
                        source_kind=source_kind, stale_after_sec=stale,
                    )
                return
            # Eviction freed room — recover and recompute normally.
            self._agg_overflow.discard(m.name)
        fresh_items = [
            (val, ts) for val, ts in buf.values()
            if stale is None or (now - ts) <= stale
        ]
        agg = _aggregate([val for val, _ in fresh_items], m.aggregate or "sum")
        if stale is None or not fresh_items:
            expires_at = None
        else:
            expires_at = min(ts for _, ts in fresh_items) + stale
        if not force:
            cur = self._cache.get(m.name)
            if cur is not None and cur.value == agg and cur.expires_at == expires_at:
                return
        await self._cache.set(
            m.name, agg, source_topic=source_topic, source_kind=source_kind,
            stale_after_sec=stale, expires_at=expires_at,
        )

    def overflowed_aggregates(self) -> list[str]:
        """Names of aggregates currently over budget with an invalidated
        output (audit D1-01). Surfaced as a metric for observability."""
        return sorted(self._agg_overflow)

    def _evict_stale_members(
        self, m: VarMapping, buf: dict[str, Any], now: float
    ) -> None:
        """Delete members past their freshness deadline from the buffer
        (audit D1-01). Only time-bounded (``stale_after_sec``) aggregates evict
        here; a no-TTL aggregate never expires members and is bounded instead
        by the member budget enforced at admission."""
        stale = m.stale_after_sec
        if stale is None or not buf:
            return
        expired = [t for t, (_v, ts) in buf.items() if (now - ts) > stale]
        for t in expired:
            del buf[t]

    def _lookup(self, topic: str, input_id: int | None = None) -> list[VarMapping]:
        """Return all variables interested in this topic that are bound to
        ``input_id`` (or unbound). Source isolation per audit A32."""
        def bound(m: VarMapping) -> bool:
            # Unbound mappings (input_id None) accept any source. A bound
            # mapping only accepts its own input; when the caller doesn't
            # know the input (input_id None) only unbound mappings match.
            return m.input_id is None or m.input_id == input_id

        out: list[VarMapping] = []
        if topic in self._exact_index:
            out.extend(m for m in self._exact_index[topic] if bound(m))
        for pattern, ms in self._wildcard_index.items():
            if _topic_matches(pattern, topic):
                out.extend(m for m in ms if bound(m))
        return out

    @staticmethod
    def _topics_for(m: VarMapping) -> list[str]:
        if m.source == "mqtt" and m.topic:
            return [m.topic]
        if m.source == "aggregate":
            return list(m.topics or [])
        return []


# ── Helpers ───────────────────────────────────────────────────────


def _min_deadline(*vals: float | None) -> float | None:
    """The soonest of several monotonic deadlines, treating ``None`` as
    "no deadline" (audit B-04). Returns ``None`` only when every value is
    ``None`` — i.e. nothing constrains the freshness."""
    present = [v for v in vals if v is not None]
    return min(present) if present else None


def _topic_matches(pattern: str, topic: str) -> bool:
    """MQTT topic match (same logic as inputs/mqtt.py)."""
    p = pattern.split("/")
    t = topic.split("/")
    i = 0
    for seg in p:
        if seg == "#":
            return True
        if i >= len(t):
            return False
        if seg == "+" or seg == t[i]:
            i += 1
            continue
        return False
    return i == len(t)


_MISSING = object()


def _extract_typed(payload: Any, json_path: str | None, value_type: str) -> Any:
    """Extract a value via dot-path and coerce to type.

    Returns the sentinel ``_MISSING`` when the path doesn't resolve
    (caller should skip this update — the source didn't supply it).
    Returns ``None`` when the path resolves to JSON null — this is a
    legitimate value and should be propagated so the cache invalidates
    stale prior values (audit 2026-05-15: dg.cap_w stayed at 45000
    during no_data because JSON-null was being silently dropped)."""
    if json_path:
        if not isinstance(payload, dict):
            return _MISSING
        obj: Any = payload
        for part in json_path.split("."):
            if not isinstance(obj, dict) or part not in obj:
                return _MISSING
            obj = obj[part]
        if obj is None:
            return None
        return _coerce(obj, value_type)
    if payload is None:
        return None
    return _coerce(payload, value_type)


def _finite(value: Any) -> Any:
    """``value`` with every non-finite float inside it replaced by None."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


def _coerce(value: Any, t: str) -> Any:
    """Best-effort type coercion."""
    if value is None:
        return None
    try:
        if t == "number":
            num = float(int(value)) if isinstance(value, bool) else float(value)
            # nan/inf are valid Python floats but invalid JSON: MySQL rejects the
            # vars_payload insert, silently losing the alert each cycle (C-03).
            return num if math.isfinite(num) else None
        if t == "bool":
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        if t == "string":
            return str(value)
        if t == "json":
            # Publishers emit NaN / Infinity inside objects (``json.loads``
            # accepts them); they are not JSON and break whatever stores or
            # serialises the value later. Same rule as for numbers: None.
            return _finite(value)
    except (TypeError, ValueError):
        return None
    return value


def _aggregate(values: Any, op: str) -> Any:
    nums = [v for v in values if isinstance(v, int | float) and not isinstance(v, bool)]
    if not nums:
        return None
    if op == "sum":
        result = sum(nums)
    elif op == "avg":
        result = sum(nums) / len(nums)
    elif op == "max":
        result = max(nums)
    elif op == "min":
        result = min(nums)
    else:
        return None
    # Arithmetic after intake can overflow (two 1e308 readings): an infinity
    # is not JSON and broke /v1/state and the live frames — same rule as at
    # intake, None (review K19).
    return _finite(result)
