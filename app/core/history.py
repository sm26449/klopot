"""History of the variables that rule expressions look back on (ADR-0004).

``avg_over("x", "5m")`` and its siblings need the recent past of ``x``; the
state cache keeps only its latest value. This store keeps, in memory, exactly
the variables and windows the enabled rules and computed formulas ask for —
derived from their expressions at every reload, nothing to configure — and
answers the window queries.

Values are a step function: a value holds until the next one (our producers
publish on change), so averages are time-weighted. Each variable keeps at most
``BUCKETS`` buckets over its longest window; samples closer than one bucket
are merged (the bucket keeps its last value as the level and the min / max it
saw), so min and max stay exact and the average is exact to a bucket.

Until the history covers a window the query raises :class:`MissingHistory`,
which the evaluator reports as a missing input (the rule is ``no_data``).
"""
from __future__ import annotations

import ast
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

BUCKETS = 2000
MAX_WINDOW_SEC = 24 * 3600
# name, window (seconds) or None for prev()
WINDOW_FUNCTIONS = frozenset({"avg_over", "min_over", "max_over", "delta", "rate", "changed"})
HISTORY_FUNCTIONS = WINDOW_FUNCTIONS | {"prev"}

_WINDOW = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(s|m|h)\s*$")
_UNIT = {"s": 1, "m": 60, "h": 3600}


class MissingHistory(TypeError):
    """The history does not cover the window (yet): a missing input."""

    def __init__(self, name: str, why: str) -> None:
        super().__init__(f"{name}: {why}")
        self.name = name


def parse_window(text: Any) -> float:
    """``"30s"`` / ``"5m"`` / ``"2h"`` → seconds; ValueError otherwise."""
    m = _WINDOW.match(text) if isinstance(text, str) else None
    if m is None:
        raise ValueError(f"window must be like \"30s\", \"5m\" or \"2h\", got {text!r}")
    sec = float(m.group(1)) * _UNIT[m.group(2)]
    if not 0 < sec <= MAX_WINDOW_SEC:
        raise ValueError(f"window must be between 1s and 24h, got {text!r}")
    return sec


def history_problem(call: ast.Call) -> str | None:
    """Write-time check of one history call (the name and window must be
    string literals, so every need is known when the rule is saved)."""
    fn = call.func.id  # type: ignore[attr-defined]
    want = 1 if fn == "prev" else 2
    args = call.args
    if len(args) != want or not all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in args):
        if fn == "prev":
            return 'prev() takes the variable name in quotes: prev("name")'
        return f'{fn}() takes the variable name and the window in quotes: {fn}("name", "5m")'
    if fn != "prev":
        try:
            parse_window(args[1].value)  # type: ignore[attr-defined]
        except ValueError as e:
            return f"{fn}(): {e}"
    return None


def needs_of(expr: str | None) -> dict[str, float]:
    """``{variable: longest window in seconds}`` an expression reads through
    the history functions (0 for ``prev`` only)."""
    out: dict[str, float] = {}
    if not expr or not any(fn + "(" in expr for fn in HISTORY_FUNCTIONS):
        return out
    from .eval import _substitute_dots  # local: eval imports this module
    try:
        tree = ast.parse(_substitute_dots(expr, {})[0], mode="eval")
    except (SyntaxError, ValueError):
        return out
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in HISTORY_FUNCTIONS and history_problem(node) is None):
            name = node.args[0].value  # type: ignore[attr-defined]
            win = 0.0 if node.func.id == "prev" else parse_window(node.args[1].value)  # type: ignore[attr-defined]
            out[name] = max(out.get(name, 0.0), win)
    return out


def merge_needs(exprs: Any) -> dict[str, float]:
    """:func:`needs_of` over several expressions, longest window wins."""
    out: dict[str, float] = {}
    for expr in exprs:
        for name, win in needs_of(expr).items():
            out[name] = max(out.get(name, 0.0), win)
    return out


def _num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


@dataclass
class _Bucket:
    t: float           # monotonic time of its first sample
    v: Any             # its last value: the level from t until the next bucket
    lo: Any            # min / max of the numeric values it saw (None if none)
    hi: Any
    changed: bool      # it saw a value different from the level before it


@dataclass
class Series:
    window: float                       # longest window asked for (0 = prev only)
    buckets: deque[_Bucket] = field(default_factory=deque)
    prev: Any = None                    # the value before the current one
    has_prev: bool = False

    @property
    def width(self) -> float:
        return self.window / BUCKETS

    def add(self, t: float, v: Any) -> None:
        last = self.buckets[-1] if self.buckets else None
        if last is not None and v == last.v:
            return                      # same level: the step function goes on
        if last is not None:
            self.prev, self.has_prev = last.v, True
        if last is not None and t - last.t < self.width:
            last.v = v
            last.changed = True
            if _num(v):
                last.lo = v if last.lo is None else min(last.lo, v)
                last.hi = v if last.hi is None else max(last.hi, v)
        else:
            self.buckets.append(_Bucket(t, v, v if _num(v) else None, v if _num(v) else None, last is not None))
        self._trim(t)

    def _trim(self, now: float) -> None:
        # Keep one bucket at or before the window's start: its level holds there.
        horizon = now - self.window
        while len(self.buckets) >= 2 and self.buckets[1].t <= horizon:
            self.buckets.popleft()
        while len(self.buckets) > BUCKETS + 1:
            self.buckets.popleft()

    # ── Queries ────────────────────────────────────────────────────

    def _window(self, name: str, window: float, now: float) -> tuple[Any, list[_Bucket], float]:
        """(level at the window's start, the buckets inside it, start)."""
        start = now - window
        if not self.buckets or self.buckets[0].t > start:
            have = now - self.buckets[0].t if self.buckets else 0.0
            raise MissingHistory(name, f"history {_fmt(have)} of {_fmt(window)}")
        before = [b for b in self.buckets if b.t <= start]
        inside = [b for b in self.buckets if b.t > start]
        return before[-1].v, inside, start

    def numeric(self, name: str, window: float, now: float) -> tuple[float, list[_Bucket], float]:
        level, inside, start = self._window(name, window, now)
        if not _num(level) or not all(_num(b.v) for b in inside):
            raise MissingHistory(name, "not a number")
        return level, inside, start

    def avg(self, name: str, window: float, now: float) -> float:
        level, inside, start = self.numeric(name, window, now)
        area, t, cur = 0.0, start, level
        for b in inside:
            area += cur * (b.t - t)
            t, cur = b.t, b.v
        area += cur * (now - t)
        return area / window

    def extreme(self, name: str, window: float, now: float, pick: Any) -> float:
        level, inside, _ = self.numeric(name, window, now)
        values = [level] + [x for b in inside for x in (b.lo, b.hi, b.v) if x is not None]
        return float(pick(values))

    def delta(self, name: str, window: float, now: float) -> float:
        level, inside, _ = self.numeric(name, window, now)
        current = inside[-1].v if inside else level
        return float(current - level)

    def changed_in(self, name: str, window: float, now: float) -> bool:
        _, inside, _ = self._window(name, window, now)
        return any(b.changed for b in inside)


def _fmt(sec: float) -> str:
    if sec >= 3600:
        return f"{sec / 3600:.1f}h"
    if sec >= 120:
        return f"{sec / 60:.0f}m"
    return f"{sec:.0f}s"


class HistoryStore:
    """The tracked variables. Needs come from named sources (``rules`` from
    the engine, ``computed`` from the input manager) and are merged; the
    store subscribes to the state cache's writes."""

    def __init__(self, cache: Any = None, max_vars: int = 200) -> None:
        self._series: dict[str, Series] = {}
        self._needs: dict[str, dict[str, float]] = {}
        self._cache = cache
        self.max_vars = max_vars
        self.dropped: list[str] = []    # needed but over max_vars
        if cache is not None:
            cache.subscribe(self._on_set)

    def tracked(self) -> dict[str, float]:
        return {n: s.window for n, s in self._series.items()}

    def set_needs(self, source: str, needs: dict[str, float]) -> None:
        self._needs[source] = dict(needs)
        merged: dict[str, float] = {}
        for part in self._needs.values():
            for name, win in part.items():
                merged[name] = max(merged.get(name, 0.0), win)
        names = sorted(merged)
        keep, self.dropped = names[: self.max_vars], names[self.max_vars:]
        if self.dropped:
            logger.warning("history: %d variable(s) over ALERTD_HISTORY_MAX_VARS=%d not tracked: %s",
                           len(self.dropped), self.max_vars, ", ".join(self.dropped[:10]))
        series: dict[str, Series] = {}
        for name in keep:
            old = self._series.get(name)
            if old is not None and old.window == merged[name]:
                series[name] = old
                continue
            fresh = Series(window=merged[name])
            if old is not None:             # a new window: re-bucket what we have
                for b in old.buckets:
                    fresh.add(b.t, b.v)
                fresh.prev, fresh.has_prev = old.prev, old.has_prev
            elif self._cache is not None:   # the value now has held since its last update
                snap = self._cache.get(name)
                if snap is not None:
                    fresh.add(snap.ts, snap.value)
            series[name] = fresh
        self._series = series
        from ..metrics import HISTORY_TRACKED_VARS
        HISTORY_TRACKED_VARS.set(len(series))

    async def _on_set(self, name: str, snap: Any) -> None:
        s = self._series.get(name)
        if s is not None:
            s.add(snap.ts, snap.value)

    def series(self, name: str) -> Series:
        s = self._series.get(name)
        if s is None:
            why = "history limit reached (ALERTD_HISTORY_MAX_VARS)" if name in self.dropped \
                else "no history: not used by a saved, enabled rule"
            raise MissingHistory(name, why)
        if self._cache is not None:
            snap = self._cache.get(name)
            if snap is not None and snap.is_stale():
                raise MissingHistory(name, "stale")
        return s


def build_functions(store: HistoryStore | None) -> dict[str, Any]:
    """The expression functions over ``store`` (no store: nothing tracked)."""
    def series(name: str) -> Series:
        if store is None:
            raise MissingHistory(name, "no history")
        return store.series(name)

    def avg_over(name: str, window: str) -> float:
        return series(name).avg(name, parse_window(window), time.monotonic())

    def min_over(name: str, window: str) -> float:
        return series(name).extreme(name, parse_window(window), time.monotonic(), min)

    def max_over(name: str, window: str) -> float:
        return series(name).extreme(name, parse_window(window), time.monotonic(), max)

    def delta(name: str, window: str) -> float:
        return series(name).delta(name, parse_window(window), time.monotonic())

    def rate(name: str, window: str) -> float:
        sec = parse_window(window)
        return series(name).delta(name, sec, time.monotonic()) / sec

    def changed(name: str, window: str) -> bool:
        return series(name).changed_in(name, parse_window(window), time.monotonic())

    def prev(name: str) -> Any:
        s = series(name)
        if not s.has_prev:
            raise MissingHistory(name, "no previous value yet")
        return s.prev

    return {"avg_over": avg_over, "min_over": min_over, "max_over": max_over,
            "delta": delta, "rate": rate, "changed": changed, "prev": prev}


_store: HistoryStore | None = None


def get_history_store() -> HistoryStore:
    """The process's store, bound to the process's state cache (a new one
    when the cache was replaced, as tests do)."""
    global _store
    from .state_cache import get_state_cache
    cache = get_state_cache()
    if _store is None or _store._cache is not cache:
        from ..config import get_settings
        _store = HistoryStore(cache, get_settings().history_max_vars)
    return _store


def reset_history_store_for_tests() -> None:
    global _store
    _store = None
