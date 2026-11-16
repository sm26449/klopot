"""A-01: the expression evaluator must reject anything outside the documented
language contract BEFORE evaluating it.

simpleeval/EvalWithCompoundTypes permits attribute/method access, so a
read-scoped caller could submit e.g. ``"a".rjust(5_000_000)`` — a method call
that allocates a huge string, bypassing simpleeval's ``*``/length guards and
exhausting memory. The AST allowlist rejects method/attribute access,
comprehensions, lambdas, set literals, oversized/over-nested expressions, and
bounds ``**`` at runtime — while still accepting every construct the contract
documents and every real stored rule.
"""
from __future__ import annotations

import pytest

from app.core.eval import ExpressionError, evaluate, validate_expression

# ── The exploit and its siblings are rejected ─────────────────────────

_BLOCKED = [
    '"a".rjust(5000000)',           # method call on a string literal (the exploit)
    '"a".zfill(3000000) == ""',     # method call on a string literal
    'len("abc".upper())',           # method call
    '"abc".__class__ == 1',         # bare attribute access on a literal
    "[0 for _ in range(100)]",      # list comprehension
    "{k: 0 for k in [1, 2, 3]}",    # dict comprehension
    "(x for x in [1, 2, 3])",       # generator
    "{1, 2, 3}",                    # set literal
    "(lambda: 1)()",                # lambda
]


@pytest.mark.parametrize("expr", _BLOCKED)
async def test_blocked_constructs_do_not_evaluate(expr):
    r = evaluate(expr, {})
    assert r.ok is False
    assert r.value is None            # no allocation / no result escaped
    with pytest.raises(ExpressionError):
        validate_expression(expr)


async def test_method_allocation_is_prevented_not_just_flagged():
    """The security property: the giant string is never built. If the allowlist
    regressed, this would allocate ~5 MB and return its length."""
    r = evaluate('len("a".rjust(5000000))', {})
    assert r.ok is False
    assert r.value is None


async def test_power_exponent_is_bounded():
    assert evaluate("10 ** 100", {}).ok is True        # small, fine
    big = evaluate("10 ** 5000", {})                   # would be a 5000-digit int
    assert big.ok is False
    # Even when the exponent comes from context (static AST can't see it).
    assert evaluate("2 ** n", {"n": 9999}).ok is False


async def test_oversized_and_overnested_rejected():
    assert evaluate("1 + " * 600 + "1", {}).ok is False     # > length cap
    # Real AST depth (redundant parens collapse): 50 nested calls.
    deep = "abs(" * 50 + "1" + ")" * 50
    assert evaluate(deep + " > 0", {}).ok is False          # > depth cap


# ── Everything the contract documents still works ─────────────────────

_ALLOWED = [
    "soc < 20",
    "var_age('battery.soc') < 900 AND battery.soc < 10",
    "max(a, b, c) > 5000 AND min(a, b, c) / max(a, b, c) < 0.65",
    "dow_now() in [5, 6]",
    "sum([1, 2, 3]) > 5",
    "avg([10, 20, 30]) > 15",
    "{'a': 1, 'b': 2}['a'] == 1",
    "[10, 20, 30][0] > 5",
    "'a' + 'b' == 'ab'",
    "hour_now() % 2 == 0",
    "2 ** 3 == 8",
    "(x if x > 0 else 0) < 20",
    "'x' not in ['a', 'b']",
    "regex_match('abc', '^a')",
    "not ac.actual_online and var_age('ac.actual_online') < 300",
]


@pytest.mark.parametrize("expr", _ALLOWED)
async def test_documented_constructs_pass_validation(expr):
    validate_expression(expr)   # must not raise


async def test_valid_expression_still_evaluates_correctly():
    assert evaluate("soc < 20", {"soc": 10}).value is True
    assert evaluate("max(a, b)", {"a": 3, "b": 7}).value == 7
    assert evaluate("dow_now() in [0,1,2,3,4,5,6]", {}).value is True


async def test_empty_expression_is_allowed():
    validate_expression("")
    validate_expression("   ")
    assert evaluate("", {}).ok is True
