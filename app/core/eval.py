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
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import re2
from simpleeval import EvalWithCompoundTypes, FunctionNotDefined, NameNotDefined

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
    if _ast_depth(tree) > _MAX_AST_DEPTH:
        return f"expression nested too deeply (> {_MAX_AST_DEPTH})"
    return None


def validate_expression(expr: str) -> None:
    """Raise :class:`ExpressionError` if ``expr`` is outside the documented
    language contract (audit A-01). Used at write time — rule create/update,
    config import, the validate endpoint — so a dangerous expression is refused
    before it is ever stored or evaluated. Evaluation re-checks the same way.

    An empty expression is allowed (the engine treats it as ``False``)."""
    if not expr or not expr.strip():
        return
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
        and not _PLACEHOLDER.match(n.id)
    }
    return frozenset((simple - func_names) | set(dotted))


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
        if n > 0 and _deep_len(seq, _MAX_SEQ_LEN) * n > _MAX_SEQ_LEN:
            raise ExpressionError("result too large")
    elif isinstance(a, int) and isinstance(b, int):
        if a.bit_length() + b.bit_length() > _MAX_RESULT_BITS:
            raise ExpressionError("result too large")
    return a * b


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
        if original.lower() in {"true", "false", "and", "or", "not", "none", "null"}:
            return original
        if original in mapping:
            return mapping[original]
        if original not in ctx:
            missing.append(original)
            # Bind it to None instead of leaving the bare name: a whole
            # namespace goes missing whenever every variable in it is stale
            # (the inverters' voltages at sunset/dawn), and NameError there
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


def _avg(values: Any) -> float:
    nums = [float(v) for v in values if v is not None]
    return sum(nums) / len(nums) if nums else 0.0


def _contains(s: Any, sub: Any) -> bool:
    if s is None:
        return False
    return str(sub) in str(s)


def _startswith(s: Any, prefix: Any) -> bool:
    return str(s or "").startswith(str(prefix))


def _endswith(s: Any, suffix: Any) -> bool:
    return str(s or "").endswith(str(suffix))


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


def _regex_match(s: Any, pattern: str) -> bool:
    if s is None:
        return False
    pat = str(pattern)
    subj = str(s)
    if len(pat) > _REGEX_MAX_PATTERN or len(subj) > _REGEX_MAX_SUBJECT:
        # Oversized pattern/subject — refuse rather than spend the work.
        return False
    try:
        rx = _compile_re2(pat)
    except Exception:
        # Invalid pattern, or one RE2 can't represent (backreference /
        # lookaround). Fail closed — never hand it to a backtracking engine.
        return False
    try:
        return bool(rx.search(subj))
    except Exception:
        return False


def _build_time_helpers(tz_name: str) -> dict[str, Any]:
    """Time helpers bound to a specific timezone (configured in settings)."""
    tz = ZoneInfo(tz_name)

    def now() -> float:
        return _time.time()

    def hour_now() -> int:
        return datetime.now(tz).hour

    def dow_now() -> int:
        return datetime.now(tz).weekday()

    def in_window(start_h: int, end_h: int) -> bool:
        h = datetime.now(tz).hour
        if start_h <= end_h:
            return start_h <= h < end_h
        # Crosses midnight (e.g., 22..6)
        return h >= start_h or h < end_h

    def since_seconds(ts: float | None) -> float:
        if ts is None:
            return float("inf")
        return now() - float(ts)

    return {
        "now": now,
        "hour_now": hour_now,
        "dow_now": dow_now,
        "in_window": in_window,
        "since_seconds": since_seconds,
    }


def _build_var_age(state_cache: Any) -> Any:
    """Returns a ``var_age(name)`` function bound to the state cache."""
    def var_age(name: str) -> float:
        snap = state_cache.get(name) if state_cache else None
        if snap is None:
            return float("inf")
        return snap.age_sec()
    return var_age


# ── Public surface ────────────────────────────────────────────────


def make_evaluator(
    *,
    timezone: str = "UTC",
    state_cache: Any = None,
) -> EvalWithCompoundTypes:
    """Construct a simpleeval instance with our function whitelist.

    Reused across many evals (cheap to construct, but repeated work
    if every rule rebuilds it). Engine builds one per tick.
    """
    funcs = {
        # Numeric
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "clamp": _clamp,
        "sum": sum,
        "avg": _avg,
        "int": int,
        "float": float,
        "bool": bool,
        # String
        "contains": _contains,
        "startswith": _startswith,
        "endswith": _endswith,
        "len": len,
        "lower": str.lower,
        "upper": str.upper,
        "regex_match": _regex_match,
    }
    funcs.update(_build_time_helpers(timezone))
    if state_cache is not None:
        funcs["var_age"] = _build_var_age(state_cache)

    e = EvalWithCompoundTypes(functions=funcs)
    # Bound `**`, `*` and `%` at runtime — operand sizes come from the context
    # (e.g. `10 ** some_var`, `'x' * some_var`) and can't be caught by the static
    # AST check (audit A-01, P0-3).
    e.operators[ast.Pow] = _bounded_pow
    e.operators[ast.Mult] = _bounded_mult
    e.operators[ast.Mod] = _bounded_mod
    return e


def evaluate(
    expr: str,
    ctx: dict[str, Any],
    *,
    evaluator: EvalWithCompoundTypes | None = None,
    timezone: str = "UTC",
    state_cache: Any = None,
) -> EvalResult:
    """Evaluate a single expression against a context.

    Returns an ``EvalResult`` — never raises (apart from programmer
    errors). Operator-error cases (undefined var, type mismatch,
    syntax error) are returned as ``ok=False``.
    """
    if not expr or not expr.strip():
        return EvalResult(value=False, ok=True)

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
    # (e.g. ``soc < 20``) would surface as NameNotDefined even when
    # present in ``ctx``.
    eva_names = {k: v for k, v in ctx.items() if "." not in k}
    eva_names.update(new_ctx)

    eva = evaluator or make_evaluator(timezone=timezone, state_cache=state_cache)
    eva.names = eva_names

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
        if missing and isinstance(e, TypeError):
            # A missing dotted name is bound to None; comparing it raises
            # here. That is the rule waiting for an input (a namespace stale
            # as a whole, a collector down), not a broken rule — the caller
            # must not count it towards auto-disable (a rule over a
            # briefly silent namespace was otherwise auto-disabled).
            return EvalResult(
                value=None, ok=False,
                error=f"missing input: {', '.join(missing)} ({type(e).__name__}: {e})",
                missing_vars=missing, missing_input=True,
            )
        return EvalResult(
            value=None, ok=False, error=f"{type(e).__name__}: {e}",
            missing_vars=missing or None,
        )
