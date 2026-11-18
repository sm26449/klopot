"""Safe expression evaluator for rule conditions.

Wraps ``simpleeval`` with a fixed whitelist of names and functions
specific to alerting use cases. No imports, no comprehensions, no
attribute walking, no lambdas (all blocked by simpleeval defaults).

See ``docs/EXPRESSION_LANGUAGE.md`` for the user-facing reference.

The evaluator:

- Accepts a ``ctx`` dict where keys may contain dots (e.g.
  ``battery.soc``). simpleeval doesn't support dotted names natively,
  so we substitute a placeholder before parsing.
- Coerces ``AND/OR/NOT`` (uppercase) to ``and/or/not`` for
  Python-syntax compatibility.
- Catches every exception and returns a structured ``EvalResult``;
  the engine logs and counts errors to auto-disable broken rules.

Time-based functions and aggregation functions are bound to a
``StateCache``-aware context the engine sets up per evaluation.
"""
from __future__ import annotations

import ast
import logging
import re
import time as _time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import re2
from simpleeval import EvalWithCompoundTypes, FunctionNotDefined, NameNotDefined

from ..utils.sun import SUNRISE_ELEVATION, sun_elevation

logger = logging.getLogger(__name__)


# ── Expression AST allowlist (audit A-01) ─────────────────────────────
#
# simpleeval + EvalWithCompoundTypes permit attribute/method access, so a
# read-scoped caller could submit e.g. ``"a".rjust(5_000_000)`` — a method call
# that allocates a huge string, bypassing simpleeval's ``*`` / string-length
# guards and exhausting memory or blocking the event loop. We therefore validate
# the (dot-substituted) expression against a positive, default-deny node
# allowlist BEFORE evaluating it: only the node types the documented language
# contract uses are permitted, calls must be to bare registered names (never a
# method), and comprehensions/lambdas/attribute access are rejected outright.
# Size/depth are bounded too, and ``**`` is bounded at runtime (below).
#
# This runs on the TRANSFORMED expression, so a legitimate dotted variable
# (``battery.soc`` → placeholder ``__v0__``, a plain Name) passes while an actual
# attribute access (``x.upper()`` → ``Attribute``) is rejected.


class ExpressionError(ValueError):
    """An expression is outside the documented language contract (audit A-01)."""


_MAX_EXPR_LEN = 2000       # mirrors the condition_expr column cap
_MAX_AST_NODES = 500       # generous vs real rules; bounds pathological nesting
_MAX_AST_DEPTH = 40
# ``a ** b``: bound the exponent so a numeric arg can't allocate a giant int
# (simpleeval's default MAX_POWER is 4_000_000 → a 4M-digit number).
_MAX_POW_EXP = 1000
# Bound the SIZE of a multiply / power RESULT, so a nested or chained operator
# can't grow an int/str/list past this even when each individual step would pass
# (audit P0-3): `(9**999)**999`, `'x' * 10**9`, `[[0]*3000]*3000 == ...`. Both
# caps are far above any real rule arithmetic.
_MAX_RESULT_BITS = 100_000     # ~30k-digit integer
_MAX_SEQ_LEN = 100_000         # characters / elements produced by repetition
# ``round(x, n)``: the builtin computes ``10 ** |n|`` for an int (review K04).
_MAX_ROUND_DIGITS = 100
# Elements / characters ALL sequence ``*`` and ``+`` of one evaluation may
# produce together (review K04): each step under _MAX_SEQ_LEN still let 81
# ``[0]*99999`` in one 900-character expression build 8 M elements (~1.5 s).
_MAX_ALLOC = 1_000_000
_alloc_left: ContextVar[int | None] = ContextVar("eval_alloc_left", default=None)


def _charge(n: int) -> None:
    """Spend ``n`` of this evaluation's sequence budget (no-op outside one)."""
    left = _alloc_left.get()
    if left is None:
        return
    if n > left:
        raise ExpressionError("expression builds too much data")
    _alloc_left.set(left - n)

# Exact node types the language contract allows. Anything else is rejected.
_ALLOWED_NODES: frozenset[type] = frozenset({
    ast.Expression,
    ast.Constant,
    ast.Name, ast.Load,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.In, ast.NotIn,
    ast.Call,
    ast.IfExp,                       # ternary: a if cond else b
    ast.List, ast.Tuple, ast.Dict,   # literals (sum([..]), in [5,6], {'k':'v'})
    ast.Subscript,                   # x[0], d['key']
})


def _ast_depth(node: ast.AST) -> int:
    return 1 + max((_ast_depth(c) for c in ast.iter_child_nodes(node)), default=0)


@lru_cache(maxsize=1024)
def _expr_rejection(transformed: str) -> str | None:
    """Return a human-readable rejection reason if the transformed expression is
    outside the allowlist, else ``None``. Cached because the engine re-evaluates
    the same stored expression every tick (audit A-01)."""
    if len(transformed) > _MAX_EXPR_LEN:
        return f"expression too long (> {_MAX_EXPR_LEN} chars)"
    try:
        tree = ast.parse(transformed, mode="eval")
    except SyntaxError as e:
        return f"syntax error: {e.msg}"
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > _MAX_AST_NODES:
            return f"expression too complex (> {_MAX_AST_NODES} nodes)"
        nt = type(node)
        if nt not in _ALLOWED_NODES:
            # Name the construct the author tried to use, not the AST class.
            friendly = {
                ast.Attribute: "attribute / method access",
                ast.ListComp: "list comprehension",
                ast.SetComp: "set comprehension",
                ast.DictComp: "dict comprehension",
                ast.GeneratorExp: "generator expression",
                ast.Lambda: "lambda",
                ast.Set: "set literal",
                ast.Slice: "slice",
                ast.Starred: "argument unpacking",
            }.get(nt, nt.__name__)
            return f"{friendly} is not allowed in expressions"
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                return "only direct calls to named functions are allowed"
            if node.keywords:
                return "keyword arguments are not allowed in function calls"
            if node.func.id not in FUNCTION_NAMES:
                return f"unknown function: {node.func.id}()"
            if (node.func.id == "regex_match" and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                problem = _regex_problem(node.args[1].value)
                if problem is not None:
                    return problem
    if _ast_depth(tree) > _MAX_AST_DEPTH:
        return f"expression nested too deeply (> {_MAX_AST_DEPTH})"
    return None


def _source_rejection(expr: str) -> str | None:
    """Reasons to refuse the raw source before it is masked (review K20):
    the masker marks string literals with ``\x00S<n>\x00``, so a control
    character in the source could forge a marker, and it masks only single-
    and double-quoted literals, so a triple-quoted one is split in pieces."""
    if any((ord(c) < 32 and c not in "\t\n\r") or ord(c) == 127 for c in expr):
        return "control characters are not allowed in expressions"
    if '"""' in expr or "'''" in expr:
        return "triple-quoted strings are not supported; use '...' or \"...\""
    return None


def validate_expression(expr: str) -> None:
    """Raise :class:`ExpressionError` if ``expr`` is outside the documented
    language contract (audit A-01). Used at write time — rule create/update,
    config import, the validate endpoint — so a dangerous expression is refused
    before it is ever stored or evaluated. Evaluation re-checks the same way.

    An empty expression is allowed (the engine treats it as ``False``)."""
    if not expr or not expr.strip():
        return
    reason = _source_rejection(expr)
    if reason is not None:
        raise ExpressionError(reason)
    transformed, _, _ = _substitute_dots(expr, {})
    reason = _expr_rejection(transformed)
    if reason is not None:
        raise ExpressionError(reason)


_PLACEHOLDER = re.compile(r"^__v\d+__$")


@lru_cache(maxsize=512)
def referenced_names(expr: str) -> frozenset[str]:
    """The variable names a formula reads (audit B-04).

    Returns both simple identifiers and dotted references (which are cache
    keys in their own right), excluding function-call targets, language
    keywords and anything inside a string literal. Used to bound a computed
    variable's freshness by the deadlines of the dependencies it actually
    reads, so a long-TTL computed can't outlive a short-TTL input.

    A name referenced only inside a string — e.g. ``var_age("soc")`` — is
    deliberately not reported: those bypass the evaluation context, and the
    computed's own TTL plus the clock sweep still bound it. On any parse
    trouble this returns the empty set (no bounding, never a wrong bound).
    """
    if not expr or not expr.strip():
        return frozenset()
    try:
        transformed, _ctx, dotted = _substitute_dots(expr, {})
        tree = ast.parse(transformed, mode="eval")
    except (SyntaxError, ValueError):
        return frozenset()
    func_names = {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    simple = {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        and not _PLACEHOLDER.match(n.id) and n.id.lower() not in KEYWORD_WORDS
    }
    return frozenset((simple - func_names) | set(dotted))


# Functions whose first argument is a variable name in quotes.
_NAME_ARG_FUNCTIONS = frozenset({"var_age", "fresh", "has"})


def display_names(expr: str) -> list[str]:
    """Variables an expression reads, for the editor (review RL-04): the
    names of :func:`referenced_names` plus the string arguments of
    ``var_age("…")``, ``fresh("…", s)`` and ``has("…")``, in order of first
    appearance. Text inside other string
    literals (``contains(x, 'STATUS')``) is never reported."""
    names = set(referenced_names(expr))
    try:
        transformed, _ctx, _dotted = _substitute_dots(expr, {})
        tree = ast.parse(transformed, mode="eval")
    except (SyntaxError, ValueError):
        tree = None
    if tree is not None:
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _NAME_ARG_FUNCTIONS
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                names.add(n.args[0].value)
    return sorted(names, key=lambda n: (expr.find(n) if n in expr else len(expr), n))


@lru_cache(maxsize=1024)
def _simple_names(transformed: str) -> frozenset[str]:
    """Undotted names a (transformed) expression reads as values — not
    function names, placeholders or keywords."""
    try:
        tree = ast.parse(transformed, mode="eval")
    except SyntaxError:
        return frozenset()
    funcs = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return frozenset(
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id not in funcs
        and not _PLACEHOLDER.match(n.id) and n.id.lower() not in KEYWORD_WORDS
    )


def _deep_len(x: Any, budget: int) -> int:
    """Total (deeply nested) element count of a sequence, short-circuiting once
    it passes ``budget`` so the measurement itself can't be the DoS. Strings and
    bytes count as their length (no char-by-char recursion); scalars count as 1.
    """
    if isinstance(x, str | bytes):
        return len(x)
    if not isinstance(x, list | tuple):
        return 1
    total = 0
    for el in x:
        total += _deep_len(el, budget - total)
        if total > budget:
            break
    return total


def _bounded_pow(a: Any, b: Any) -> Any:
    """``a ** b`` with the exponent AND the result size bounded (audit A-01,
    P0-3). A bounded exponent alone isn't enough: ``(big ** 999)`` feeds a huge
    base into the next power, so reject before computing when the estimated
    result (base bits × exponent) would exceed the cap."""
    if isinstance(b, int | float) and abs(b) > _MAX_POW_EXP:
        raise ExpressionError(f"exponent too large (> {_MAX_POW_EXP})")
    if isinstance(a, int) and isinstance(b, int) and b > 0 and not isinstance(a, bool):
        if a.bit_length() * b > _MAX_RESULT_BITS:
            raise ExpressionError("result too large")
    return a ** b


def _bounded_mult(a: Any, b: Any) -> Any:
    """``a * b`` bounding both sequence repetition and big-int growth (P0-3).
    ``seq * n`` repeats a string/list/tuple — cap the deep element count so a
    nested ``[[0]*n]*n`` can't be built (and then compared in n² time)."""
    seq, n = (a, b) if isinstance(a, str | bytes | list | tuple) else (b, a)
    if isinstance(seq, str | bytes | list | tuple) and isinstance(n, int) and not isinstance(n, bool):
        size = _deep_len(seq, _MAX_SEQ_LEN) * n if n > 0 else 0
        if size > _MAX_SEQ_LEN:
            raise ExpressionError("result too large")
        _charge(size)
    elif isinstance(a, int) and isinstance(b, int):
        if a.bit_length() + b.bit_length() > _MAX_RESULT_BITS:
            raise ExpressionError("result too large")
    return a * b


def _charged_add(add: Any) -> Any:
    """simpleeval's ``+`` (which caps one result at 100 k) charged to the
    evaluation's sequence budget, so a chain of additions cannot add up."""
    def _add(a: Any, b: Any) -> Any:
        result = add(a, b)
        if isinstance(result, str | bytes | list | tuple):
            _charge(len(result))
        return result
    return _add


def _bounded_mod(a: Any, b: Any) -> Any:
    """``a % b`` — numeric modulo only. printf-style string formatting is
    rejected: ``'%20000000d' % 1`` expands a tiny expression into megabytes via
    a width specifier, and the language has no need for it (audit P0-3)."""
    if isinstance(a, str | bytes):
        raise ExpressionError("string formatting with % is not allowed")
    return a % b


# Pattern for dotted variable references — replaced before eval
_DOTTED = re.compile(r"\b([a-z_][\w]*\.[a-z_][\w.]*)", re.IGNORECASE)
# Match single- or double-quoted string literals. Used to mask string
# contents during dot-substitution so that names INSIDE a string (e.g.
# ``var_age("ov.f1.state")``) are not rewritten and broken.
_STRINGS = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'')


# Words the expression language treats as literals / operators in any case
# (``false``, ``NULL``, ``And``…), never as variable names (audit B07).
KEYWORD_WORDS = frozenset({"true", "false", "and", "or", "not", "none", "null"})

# ``true`` / ``false`` / ``null`` / ``none`` in lower, upper or capitalised
# form are literals (review RL-08), like Python's ``True`` / ``False`` / ``None``.
_LITERAL_NAMES: dict[str, Any] = {
    form: value
    for word, value in (("true", True), ("false", False), ("null", None), ("none", None))
    for form in (word, word.upper(), word.capitalize())
    if form not in ("True", "False", "None")
}

# Prefix of EvalResult.error for a rule waiting on an input (not a broken
# rule). The rules API derives eval_status="no_data" from it.
MISSING_INPUT_PREFIX = "missing input: "


@dataclass
class EvalResult:
    """Outcome of one evaluation."""

    value: Any
    ok: bool
    error: str | None = None
    missing_vars: list[str] | None = None
    missing_input: bool = False      # not ok because an input the rule needs is absent, not because the rule is wrong


def _substitute_dots(expr: str, ctx: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    """Replace dotted names with simple identifiers.

    Returns (transformed_expr, new_ctx, missing_var_names).
    Identifiers without dots pass through unchanged.
    """
    counter = [0]
    mapping: dict[str, str] = {}     # original → placeholder
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        original = m.group(1)
        if original.lower() in KEYWORD_WORDS:
            return original
        if original in mapping:
            return mapping[original]
        if original not in ctx:
            missing.append(original)
            # Bind it to None instead of leaving the bare name: a whole
            # namespace goes missing whenever every variable in it is stale
            # (e.g. every sensor of a device that went to sleep), and NameError there
            # made the rule count eval errors towards auto-disable. With
            # None the usual ``var_age(...) < N and x > y`` short-circuits on
            # the age guard; a rule that compares the None directly still
            # raises a TypeError, so a genuine typo does not go silent.
            ph = f"__v{counter[0]}__"
            counter[0] += 1
            mapping[original] = ph
            return ph
        ph = f"__v{counter[0]}__"
        counter[0] += 1
        mapping[original] = ph
        return ph

    # Mask string literals FIRST — before ANY rewriting — so neither the
    # AND/OR/NOT normalization nor the dotted-name substitution can reach inside
    # a quoted constant. Otherwise a literal like ``"NOT ready"`` would become
    # ``"not ready"`` and a valid comparison against the real text would
    # silently evaluate false (audit B-07), and dotted names inside strings
    # (e.g. ``var_age("ov.f1.state")``) would be rewritten too.
    masked_strings: list[str] = []

    def _mask(m: re.Match[str]) -> str:
        masked_strings.append(m.group(0))
        return f"\x00S{len(masked_strings) - 1}\x00"

    masked = _STRINGS.sub(_mask, expr)

    # Normalize the uppercase boolean keywords to Python syntax — now that
    # strings are masked, this only ever touches language tokens.
    masked = re.sub(r"\bAND\b", "and", masked)
    masked = re.sub(r"\bOR\b", "or", masked)
    masked = re.sub(r"\bNOT\b", "not", masked)

    masked = _DOTTED.sub(repl, masked)

    # Restore original string literals
    def _unmask(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        return masked_strings[idx]

    transformed = re.sub(r"\x00S(\d+)\x00", _unmask, masked)

    new_ctx = {ph: ctx.get(orig) for orig, ph in mapping.items()}
    return transformed, new_ctx, missing


# ── Built-in functions ────────────────────────────────────────────


def _clamp(x: float, lo: float, hi: float) -> float:
    return min(max(x, lo), hi)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float)


def _sum(values: Any, start: Any = 0) -> Any:
    """Numbers only. The builtin also adds lists and strings, inside one C call
    that the ``*`` / ``+`` bounds never see: ``sum([[0]*99999, …], [])`` held
    the GIL for seconds from an 800-character expression (review K04)."""
    items = list(values)
    if not _is_number(start) or not all(_is_number(v) for v in items):
        raise ExpressionError("sum() takes numbers only")
    return sum(items, start)


def _round(x: Any, ndigits: Any = None) -> Any:
    """``round`` with ``ndigits`` bounded: for an int, ``round(5, -9999999)``
    computes ``10 ** 9999999`` (seconds of CPU, holding the GIL)."""
    if ndigits is None:
        return round(x)
    if isinstance(ndigits, int) and abs(ndigits) > _MAX_ROUND_DIGITS:
        raise ExpressionError(f"round() ndigits out of range (> {_MAX_ROUND_DIGITS})")
    return round(x, ndigits)


class NoValues(TypeError):
    """An aggregate got no values. A ``TypeError`` so that, when the values
    are missing inputs, the rule waits for data instead of failing."""


def _avg(values: Any) -> float:
    """Mean of the values that are not ``None``. With none left it raises
    instead of returning 0, which matched every "below threshold" rule while
    its inputs were missing (review RL-07)."""
    nums = [float(v) for v in values if v is not None]
    if not nums:
        raise NoValues("avg() of no values")
    return sum(nums) / len(nums)


def _contains(s: Any, sub: Any) -> bool:
    if s is None:
        return False
    return str(sub) in str(s)


def _startswith(s: Any, prefix: Any) -> bool:
    return str(s or "").startswith(str(prefix))


def _endswith(s: Any, suffix: Any) -> bool:
    return str(s or "").endswith(str(suffix))


def _not(x: Any) -> bool:
    """``NOT x``. ``NOT`` of a missing input (``None``) is a missing input,
    not ``True``: ``NOT infra.x.running`` matched at every start, before the
    first message (review RL-41)."""
    if x is None:
        raise TypeError("NOT of None")
    return not x


def _between(x: Any, lo: Any, hi: Any) -> bool:
    """``lo <= x <= hi``. ``None`` is a missing input (the rule waits)."""
    if x is None:
        raise TypeError("between() of None")
    return bool(lo <= x <= hi)


def _coalesce(*values: Any) -> Any:
    """The first value that is not ``None`` (a missing input is ``None``)."""
    return next((v for v in values if v is not None), None)


def _sequence(values: Any, fn: str) -> list[Any] | tuple[Any, ...]:
    if not isinstance(values, list | tuple):
        raise ExpressionError(f"{fn}() takes a list: {fn}([a, b, …])")
    return values


def _any(values: Any) -> bool:
    return any(_sequence(values, "any"))


def _all(values: Any) -> bool:
    return all(_sequence(values, "all"))


# User-supplied regexes run through RE2, not Python's `re` (audit R08/V10).
# RE2 matches in time linear in the subject with NO catastrophic backtracking,
# so a pathological pattern like `(a+)+$` can't hold the GIL and freeze the
# event loop — a wall-clock budget on a worker thread never could, because a
# backtracking `re.search` doesn't release the GIL for the thread to be
# preempted. RE2 can't represent backreferences or lookaround; such a pattern
# fails to compile and we fail closed (never fall back to a backtracking
# engine). Length caps stay as a cheap additional defense.
_REGEX_MAX_PATTERN = 512
_REGEX_MAX_SUBJECT = 4096

_RE2_OPTIONS = re2.Options()
_RE2_OPTIONS.log_errors = False          # don't spam stderr on a bad user pattern
_RE2_OPTIONS.max_mem = 8 << 20           # bound the compiled program (8 MiB)


@lru_cache(maxsize=512)
def _compile_re2(pattern: str) -> Any:
    """Compile (and cache) a user pattern under RE2. Raises on an invalid or
    unsupported pattern; failures are not cached."""
    return re2.compile(pattern, options=_RE2_OPTIONS)


def _regex_problem(pattern: str) -> str | None:
    """Why ``pattern`` cannot be used by ``regex_match``, or ``None``."""
    if len(pattern) > _REGEX_MAX_PATTERN:
        return f"regex_match pattern too long (> {_REGEX_MAX_PATTERN} chars)"
    try:
        _compile_re2(pattern)
    except Exception as e:
        detail = e.args[0] if e.args else e
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        return (f"regex_match pattern not supported: {detail} "
                "(RE2 syntax: no lookahead, lookbehind or backreferences)")
    return None


def _regex_match(s: Any, pattern: str) -> bool:
    """RE2 search. A pattern RE2 cannot run, or an oversized subject, is an
    error, never a silent ``False`` (review RL-01: a rule with a lookahead
    stopped firing without any sign). It is never handed to a backtracking
    engine. A literal pattern is already refused when the expression is saved."""
    if s is None:
        return False
    pat = str(pattern)
    subj = str(s)
    problem = _regex_problem(pat)
    if problem is not None:
        raise ExpressionError(problem)
    if len(subj) > _REGEX_MAX_SUBJECT:
        raise ExpressionError(f"regex_match subject too long (> {_REGEX_MAX_SUBJECT} chars)")
    return bool(_compile_re2(pat).search(subj))


def _minute_of_day(t: Any, fn: str) -> int:
    """An hour (``8``, ``8.5``) or ``"HH:MM"`` as minutes after midnight."""
    if isinstance(t, str):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", t)
        if m is None or int(m.group(1)) > 24 or int(m.group(2)) > 59:
            raise ExpressionError(f"{fn}(): time must be an hour or 'HH:MM', got {t!r}")
        minutes = int(m.group(1)) * 60 + int(m.group(2))
    elif _is_number(t) and not isinstance(t, bool):
        minutes = round(float(t) * 60)
    else:
        raise ExpressionError(f"{fn}(): time must be an hour or 'HH:MM', got {t!r}")
    if not 0 <= minutes <= 24 * 60:
        raise ExpressionError(f"{fn}(): time out of range: {t!r}")
    return minutes


def _build_time_helpers(tz_name: str, location: tuple[float, float] | None) -> dict[str, Any]:
    """Time helpers bound to a timezone and, for the sun, a place (settings)."""
    tz = ZoneInfo(tz_name)

    def now() -> float:
        return _time.time()

    def hour_now() -> int:
        return datetime.now(tz).hour

    def dow_now() -> int:
        return datetime.now(tz).weekday()

    def month_now() -> int:
        return datetime.now(tz).month

    def is_weekend() -> bool:
        return datetime.now(tz).weekday() >= 5

    def in_window(start: Any, end: Any) -> bool:
        """``[start, end)`` in local time; an hour or ``"HH:MM"``. Crosses
        midnight when ``end < start`` (``in_window("22:30", "06:15")``)."""
        lo, hi = _minute_of_day(start, "in_window"), _minute_of_day(end, "in_window")
        t = datetime.now(tz)
        cur = t.hour * 60 + t.minute
        if lo <= hi:
            return lo <= cur < hi
        return cur >= lo or cur < hi

    def since_seconds(ts: float | None) -> float:
        if ts is None:
            return float("inf")
        return now() - float(ts)

    def _elevation(fn: str) -> float:
        if location is None:
            raise ExpressionError(f"{fn}() needs the place: set ALERTD_LATITUDE and ALERTD_LONGITUDE")
        return sun_elevation(location[0], location[1], datetime.now(tz))

    def sun_elevation_now() -> float:
        return round(_elevation("sun_elevation"), 2)

    def is_daylight() -> bool:
        return _elevation("is_daylight") > SUNRISE_ELEVATION

    return {
        "now": now,
        "hour_now": hour_now,
        "dow_now": dow_now,
        "month_now": month_now,
        "is_weekend": is_weekend,
        "in_window": in_window,
        "since_seconds": since_seconds,
        "sun_elevation": sun_elevation_now,
        "is_daylight": is_daylight,
    }


def _build_cache_helpers(state_cache: Any) -> dict[str, Any]:
    """Functions that read the state cache by name (no cache: nothing known)."""
    def var_age(name: str) -> float:
        snap = state_cache.get(name) if state_cache else None
        if snap is None:
            return float("inf")
        return float(snap.age_sec())

    def fresh(name: str, max_age_sec: float) -> bool:
        """``var_age(name) < max_age_sec``."""
        return var_age(name) < max_age_sec

    def has(name: str) -> bool:
        """The variable holds a value that is not stale."""
        snap = state_cache.get(name) if state_cache else None
        return snap is not None and snap.value is not None and not snap.is_stale()

    return {"var_age": var_age, "fresh": fresh, "has": has}


# ── Public surface ────────────────────────────────────────────────


def make_evaluator(
    *,
    timezone: str = "UTC",
    state_cache: Any = None,
    location: tuple[float, float] | None = None,
) -> EvalWithCompoundTypes:
    """Construct a simpleeval instance with our function whitelist.

    Reused across many evals (cheap to construct, but repeated work
    if every rule rebuilds it). Engine builds one per tick. ``location`` is
    (latitude, longitude) for the sun functions.
    """
    funcs: dict[str, Any] = {
        # Numeric
        "abs": abs,
        "min": min,
        "max": max,
        "round": _round,
        "clamp": _clamp,
        "sum": _sum,
        "avg": _avg,
        "int": int,
        "float": float,
        "bool": bool,
        "between": _between,
        "coalesce": _coalesce,
        "any": _any,
        "all": _all,
        # String
        "contains": _contains,
        "startswith": _startswith,
        "endswith": _endswith,
        "len": len,
        "lower": str.lower,
        "upper": str.upper,
        "regex_match": _regex_match,
    }
    funcs.update(_build_time_helpers(timezone, location))
    funcs.update(_build_cache_helpers(state_cache))

    e = EvalWithCompoundTypes(functions=funcs)
    # Bound `**`, `*` and `%` at runtime — operand sizes come from the context
    # (e.g. `10 ** some_var`, `'x' * some_var`) and can't be caught by the static
    # AST check (audit A-01, P0-3).
    e.operators[ast.Pow] = _bounded_pow
    e.operators[ast.Mult] = _bounded_mult
    e.operators[ast.Mod] = _bounded_mod
    e.operators[ast.Add] = _charged_add(e.operators[ast.Add])
    e.operators[ast.Not] = _not
    return e


# Every function an expression may call; a call to any other name is refused
# when the rule is saved (a typo would otherwise fail on every evaluation).
FUNCTION_NAMES: frozenset[str] = frozenset(make_evaluator().functions)


def evaluate(
    expr: str,
    ctx: dict[str, Any],
    *,
    evaluator: EvalWithCompoundTypes | None = None,
    timezone: str = "UTC",
    state_cache: Any = None,
    location: tuple[float, float] | None = None,
) -> EvalResult:
    """Evaluate a single expression against a context.

    Returns an ``EvalResult`` — never raises (apart from programmer
    errors). Operator-error cases (undefined var, type mismatch,
    syntax error) are returned as ``ok=False``.
    """
    if not expr or not expr.strip():
        return EvalResult(value=False, ok=True)

    rejection = _source_rejection(expr)
    if rejection is not None:
        return EvalResult(value=None, ok=False, error=rejection)

    transformed, new_ctx, missing = _substitute_dots(expr, ctx)

    # Reject anything outside the language contract BEFORE evaluating it, so an
    # attribute/method call, comprehension, oversized or over-nested expression
    # can never reach simpleeval (audit A-01). Stored rules are already validated
    # at write time; this is the eval-time backstop that also covers computed
    # variables and any path that didn't go through a write check.
    rejection = _expr_rejection(transformed)
    if rejection is not None:
        return EvalResult(value=None, ok=False, error=rejection)

    # Merge: non-dotted names pass through unchanged; dotted names
    # become placeholders. Without this merge simple-name vars
    # (e.g. ``temp > 40``) would surface as NameNotDefined even when
    # present in ``ctx``.
    eva_names = {k: v for k, v in ctx.items() if "." not in k}
    eva_names.update(new_ctx)
    # An undotted name with no value waits for data like a dotted one
    # (review RL-05): bound to None, reported as missing.
    for name in sorted(_simple_names(transformed)):
        if name not in eva_names:
            eva_names[name] = None
            missing.append(name)
    eva_names.update(_LITERAL_NAMES)
    # Inputs that are present but hold no value (an MQTT null) — a TypeError
    # on them is the rule waiting for data too (review RL-06).
    no_value = sorted(n for n in referenced_names(expr) if n in ctx and ctx[n] is None)

    eva = evaluator or make_evaluator(timezone=timezone, state_cache=state_cache, location=location)
    eva.names = eva_names

    budget = _alloc_left.set(_MAX_ALLOC)
    try:
        result = eva.eval(transformed)
        return EvalResult(value=result, ok=True, missing_vars=missing or None)
    except (NameNotDefined, FunctionNotDefined) as e:
        return EvalResult(
            value=None, ok=False, error=str(e), missing_vars=missing or None,
        )
    except SyntaxError as e:
        return EvalResult(value=None, ok=False, error=f"syntax: {e}")
    except Exception as e:
        # Includes ZeroDivisionError, TypeError, etc.
        waiting = missing + no_value
        if waiting and isinstance(e, TypeError):
            # A missing name is bound to None; comparing it raises here —
            # as does an input whose value is None. That is the rule waiting
            # for an input (a namespace stale as a whole, a collector down),
            # not a broken rule — the caller must not count it towards
            # auto-disable (a rule over a briefly silent namespace was
            # otherwise auto-disabled).
            return EvalResult(
                value=None, ok=False,
                error=f"{MISSING_INPUT_PREFIX}{', '.join(waiting)} ({type(e).__name__}: {e})",
                missing_vars=waiting, missing_input=True,
            )
        return EvalResult(
            value=None, ok=False, error=f"{type(e).__name__}: {e}",
            missing_vars=missing or None,
        )
    finally:
        _alloc_left.reset(budget)
