"""History of the variables that rule expressions look back on (ADR-0004).

``avg_over("x", "5m")`` and its siblings need the recent past of ``x``; the
state cache keeps only its latest value. This store keeps, in memory, exactly
the variables and windows the enabled rules and computed formulas ask for —
derived from their expressions at every reload, nothing to configure — and
answers the window queries.

Values are a step function: a value holds until the next one (our producers
publish on change), so averages are time-weighted. Each variable keeps its
exact change points over its longest window — at most ``MAX_POINTS``; nothing
is merged, so every answer is exact or a missing input (rc.9 review RC-02:
merged buckets gave a max of 1 for a peak of 100).

Until the history covers a window the query raises :class:`MissingHistory`,
which the evaluator reports as a missing input (the rule is ``no_data``).
"""
from __future__ import annotations

import ast
import logging
import re
import time
from array import array
from bisect import bisect_right
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

MAX_POINTS = 10_000
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
    the history functions (0 for ``prev`` only) — from the same AST the
    validator reads, so ``avg_over ("x", "5m")`` counts too (RC-05)."""
    return dict(_needs(expr or ""))


@lru_cache(maxsize=1024)
def _needs(expr: str) -> tuple[tuple[str, float], ...]:
    if not expr.strip():
        return ()
    from .eval import _substitute_dots  # local: eval imports this module
    try:
        tree = ast.parse(_substitute_dots(expr, {})[0], mode="eval")
    except (SyntaxError, ValueError):
        return ()
    out: dict[str, float] = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in HISTORY_FUNCTIONS and history_problem(node) is None):
            name = node.args[0].value  # type: ignore[attr-defined]
            win = 0.0 if node.func.id == "prev" else parse_window(node.args[1].value)  # type: ignore[attr-defined]
            out[name] = max(out.get(name, 0.0), win)
    return tuple(sorted(out.items()))


def merge_needs(exprs: Any) -> dict[str, float]:
    """:func:`needs_of` over several expressions, longest window wins."""
    out: dict[str, float] = {}
    for expr in exprs:
        for name, win in needs_of(expr).items():
            out[name] = max(out.get(name, 0.0), win)
    return out


def _num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _same(a: Any, b: Any) -> bool:
    """Equal and of the same kind (True is not 1 here)."""
    return type(a) is type(b) and a == b


@dataclass
class Series:
    """The exact change points of one variable: ``values[i]`` holds from
    ``times[i]`` until ``times[i + 1]`` (or now). Equal consecutive values
    are one point; nothing is merged, so every query is exact (RC-02). At
    most :data:`MAX_POINTS` points: past it the oldest go, and a window they
    no longer cover is a missing input — never an approximate answer."""

    window: float                       # longest window asked for (0 = prev only)
    times: array[float] = field(default_factory=lambda: array("d"))
    values: list[Any] = field(default_factory=list)
    prev: Any = None                    # the value before the current one
    has_prev: bool = False
    capped: bool = False                # points were dropped for MAX_POINTS

    def add(self, t: float, v: Any) -> None:
        if self.values and _same(v, self.values[-1]):
            return                      # same level: the step function goes on
        if self.values:
            self.prev, self.has_prev = self.values[-1], True
            t = max(t, self.times[-1])
        self.times.append(t)
        self.values.append(v)
        self._trim(t)

    def _trim(self, now: float) -> None:
        # Keep the last point at or before the window's start: its value holds there.
        i = bisect_right(self.times, now - self.window) - 1
        if i > 0:
            del self.times[:i]
            del self.values[:i]
        excess = len(self.times) - MAX_POINTS
        if excess > 0:
            del self.times[:excess]
            del self.values[:excess]
            self.capped = True

    # ── Queries ────────────────────────────────────────────────────

    def _start(self, name: str, window: float, now: float) -> int:
        """Index of the point whose value holds at the window's start."""
        start = now - window
        i = bisect_right(self.times, start) - 1
        if i < 0:
            have = now - self.times[0] if self.times else 0.0
            why = f"history {_fmt(have)} of {_fmt(window)}"
            if self.capped:
                why += f" (the last {MAX_POINTS} changes are kept)"
            raise MissingHistory(name, why)
        return i

    def _numbers(self, name: str, i: int) -> list[float]:
        vals = self.values[i:]
        if not all(_num(v) for v in vals):
            raise MissingHistory(name, "not a number")
        return vals

    def avg(self, name: str, window: float, now: float) -> float:
        i = self._start(name, window, now)
        vals = self._numbers(name, i)
        start = now - window
        area = 0.0
        for k, v in enumerate(vals):
            t0 = max(self.times[i + k], start)
            t1 = self.times[i + k + 1] if i + k + 1 < len(self.times) else now
            area += v * max(0.0, min(t1, now) - t0)
        return area / window

    def extreme(self, name: str, window: float, now: float, pick: Any) -> float:
        return float(pick(self._numbers(name, self._start(name, window, now))))

    def delta(self, name: str, window: float, now: float) -> float:
        vals = self._numbers(name, self._start(name, window, now))
        return float(vals[-1] - vals[0])

    def changed_in(self, name: str, window: float, now: float) -> bool:
        return self._start(name, window, now) < len(self.times) - 1


def _fmt(sec: float) -> str:
    if sec >= 3600:
        return f"{sec / 3600:.1f}h"
    if sec >= 120:
        return f"{sec / 60:.0f}m"
    return f"{sec:.0f}s"


class HistoryStore:
    """The tracked variables. Needs come from named sources (``rules`` from
    the engine, ``computed`` from the input manager) and are merged; the
    store follows the state cache's writes and its invalidations."""

    def __init__(self, cache: Any = None, max_vars: int = 200) -> None:
        self._series: dict[str, Series] = {}
        self._needs: dict[str, dict[str, float]] = {}
        self._cache = cache
        self.max_vars = max_vars
        self.dropped: list[str] = []    # needed but over max_vars
        if cache is not None:
            cache.subscribe(self._on_set)
            if hasattr(cache, "subscribe_clear"):
                cache.subscribe_clear(self._on_clear)

    def tracked(self) -> dict[str, float]:
        return {n: s.window for n, s in self._series.items()}

    def merged_needs(self, **replace: dict[str, float]) -> dict[str, float]:
        """Every source's needs merged; ``replace`` swaps one source's
        needs for a what-if (the write-time budget check, RC-03)."""
        merged: dict[str, float] = {}
        for part in {**self._needs, **replace}.values():
            for name, win in part.items():
                merged[name] = max(merged.get(name, 0.0), win)
        return merged

    def set_needs(self, source: str, needs: dict[str, float]) -> None:
        self._needs[source] = dict(needs)
        merged = self.merged_needs()
        # Over the budget, what is tracked already stays tracked: a new need
        # never evicts a working rule's history (RC-03; saving over the budget
        # is refused, this is the backstop).
        names = [n for n in sorted(merged) if n in self._series] + [n for n in sorted(merged) if n not in self._series]
        keep, self.dropped = names[: self.max_vars], sorted(names[self.max_vars:])
        if self.dropped:
            logger.warning("history: %d variable(s) over ALERTD_HISTORY_MAX_VARS=%d not tracked: %s",
                           len(self.dropped), self.max_vars, ", ".join(self.dropped[:10]))
        series: dict[str, Series] = {}
        for name in keep:
            old = self._series.get(name)
            if old is not None:
                old.window = merged[name]
                series[name] = old
                continue
            fresh = Series(window=merged[name])
            if self._cache is not None:     # the value now has held since its last update
                snap = self._cache.get(name)
                if snap is not None and not snap.is_stale():
                    fresh.add(snap.ts, snap.value)
            series[name] = fresh
        self._series = series
        from ..metrics import HISTORY_TRACKED_VARS
        HISTORY_TRACKED_VARS.set(len(series))

    async def _on_set(self, name: str, snap: Any) -> None:
        s = self._series.get(name)
        if s is not None:
            s.add(snap.ts, snap.value)

    def _on_clear(self, names: Any) -> None:
        """The cache dropped values (an input reconfigured): their history
        described the old binding — start it over (RC-04)."""
        for name in list(self._series) if names is None else names:
            if name in self._series:
                self._series[name] = Series(window=self._series[name].window)

    def series(self, name: str) -> Series:
        s = self._series.get(name)
        if s is None:
            why = "history limit reached (ALERTD_HISTORY_MAX_VARS)" if name in self.dropped \
                else "no history: not used by a saved, enabled rule"
            raise MissingHistory(name, why)
        if self._cache is not None:
            snap = self._cache.get(name)
            if snap is None:
                raise MissingHistory(name, "no current value")
            if snap.is_stale():
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
