"""Pure-unit tests for app.core.eval.

simpleeval handles the actual expression mechanics; what we test
here is alertd's wrapper: dotted-name substitution, AND/OR/NOT
case folding, the function whitelist, and error-translation.
"""
from __future__ import annotations

import pytest

from app.core.eval import evaluate


def test_empty_expr_returns_false_ok():
    r = evaluate("", {})
    assert r.ok is True
    assert r.value is False


def test_simple_arithmetic():
    r = evaluate("2 + 3", {})
    assert r.ok and r.value == 5


def test_simple_name_lookup():
    r = evaluate("x > 10", {"x": 15})
    assert r.ok and r.value is True


def test_dotted_name_lookup():
    r = evaluate("battery.soc < 20", {"battery.soc": 15})
    assert r.ok and r.value is True


def test_multiple_dotted_names():
    r = evaluate(
        "battery.soc < 20 AND battery.temp > 40",
        {"battery.soc": 15, "battery.temp": 45},
    )
    assert r.ok and r.value is True


def test_uppercase_and_or_not():
    r = evaluate("NOT (a OR b) AND c", {"a": False, "b": False, "c": True})
    assert r.ok and r.value is True


def test_lowercase_and_or_not_native():
    r = evaluate("a and b", {"a": True, "b": True})
    assert r.ok and r.value is True


def test_missing_dotted_var_returns_error():
    r = evaluate("missing.var > 5", {})
    assert r.ok is False
    assert r.missing_vars and "missing.var" in r.missing_vars


def test_missing_simple_var_returns_error():
    r = evaluate("undefined_var > 5", {})
    assert r.ok is False
    assert r.error and "undefined_var" in r.error


def test_syntax_error():
    r = evaluate("(x + ", {"x": 1})
    assert r.ok is False
    assert "syntax" in (r.error or "").lower()


def test_zero_division_caught():
    r = evaluate("100 / x", {"x": 0})
    assert r.ok is False
    assert "ZeroDivisionError" in (r.error or "")


def test_whitelisted_min_max():
    r = evaluate("min(a, b, c)", {"a": 5, "b": 1, "c": 3})
    assert r.ok and r.value == 1


def test_whitelisted_avg():
    r = evaluate("avg([a, b, c])", {"a": 10, "b": 20, "c": 30})
    assert r.ok and r.value == 20.0


def test_whitelisted_clamp():
    r = evaluate("clamp(x, 0, 100)", {"x": 150})
    assert r.ok and r.value == 100


def test_whitelisted_round():
    r = evaluate("round(x, 1)", {"x": 3.456})
    assert r.ok and r.value == 3.5


def test_whitelisted_string_helpers():
    # contains is case-sensitive on purpose (caller can lower() first)
    r = evaluate("contains(s, 'FAULT')", {"s": "FAULT_OVERTEMP"})
    assert r.ok and r.value is True

    r = evaluate("startswith(s, 'pre')", {"s": "prefix"})
    assert r.ok and r.value is True

    r = evaluate("endswith(s, 'fix')", {"s": "suffix"})
    assert r.ok and r.value is True


def test_whitelisted_regex_match():
    r = evaluate("regex_match(s, 'ERR_[0-9]+')", {"s": "got ERR_42"})
    assert r.ok and r.value is True


def test_regex_match_bad_pattern():
    r = evaluate("regex_match(s, '[unclosed')", {"s": "x"})
    # A bad pattern is an error, not a silent no-match (review RL-01)
    assert not r.ok and "not supported" in (r.error or "")


def test_disallowed_function_returns_error():
    """Functions not on the whitelist must not run — security gate."""
    r = evaluate("__import__('os')", {})
    assert r.ok is False


def test_evaluator_reused_for_multiple_calls():
    """Re-using the same evaluator across many rules is the engine
    fast-path; ensure it doesn't accumulate stale state."""
    from app.core.eval import make_evaluator

    e = make_evaluator(timezone="UTC")
    r1 = evaluate("a > 1", {"a": 5}, evaluator=e)
    r2 = evaluate("b < 1", {"b": 0}, evaluator=e)
    assert r1.ok and r1.value is True
    assert r2.ok and r2.value is True


def test_var_age_unbound_returns_inf():
    """When state_cache=None, var_age isn't installed — calling it
    yields a clean error rather than crashing."""
    r = evaluate("var_age('battery.soc') > 60", {})
    assert r.ok is False
    assert "var_age" in (r.error or "")


def test_var_age_with_cache():
    """A minimal fake cache suffices to verify the binding works."""

    class _FakeSnap:
        def age_sec(self) -> float:
            return 42.0

    class _FakeCache:
        def get(self, name: str) -> _FakeSnap | None:
            return _FakeSnap() if name == "battery.soc" else None

    r = evaluate(
        "var_age('battery.soc') > 30",
        {},
        state_cache=_FakeCache(),
    )
    assert r.ok and r.value is True


def test_whitespace_only_expr():
    assert evaluate("   ", {}).value is False


def test_boolean_short_circuit():
    """Verify AND/OR short-circuit semantics — a missing var to the
    right of a falsy AND should NOT throw."""
    r = evaluate("False AND undefined_var", {})
    assert r.ok and r.value is False


def test_in_window_helper():
    """Time-window helper from the whitelist."""
    # 0 to 24 always matches (any time of day)
    r = evaluate("in_window(0, 24)", {})
    assert r.ok and r.value is True

    # midnight-only window: behavior is wall-clock-dependent so just
    # confirm the helper is callable
    r = evaluate("in_window(0, 1)", {})
    assert r.ok


# ── Regression: dotted names inside string literals ──────────


def test_dotted_name_inside_string_is_preserved():
    """A dotted name inside a string literal must not be rewritten.

    Previously _substitute_dots applied the regex globally, breaking
    ``var_age("ov.f1.state")`` — the contents of the string got
    replaced with the placeholder, the function received gibberish,
    and the rule never matched (ov_recovered_fN_v1 was DOA).
    """
    # The dotted name 'ov.f1.state' appears both as a real ref and
    # inside a string argument. Only the bare ref should be replaced.
    from app.core.eval import _substitute_dots
    transformed, new_ctx, missing = _substitute_dots(
        'ov.f1.state == "normal" AND var_age("ov.f1.state") < 600',
        {"ov.f1.state": "normal"},
    )
    # Bare reference replaced
    assert "ov.f1.state ==" not in transformed
    # String literal preserved verbatim
    assert '"ov.f1.state"' in transformed
    assert missing == []
    assert "normal" in new_ctx.values()


def test_dotted_name_in_single_quotes_also_preserved():
    from app.core.eval import _substitute_dots
    transformed, _, _ = _substitute_dots(
        "a.b == 1 AND startswith(a.b, 'a.b')",
        {"a.b": "abc"},
    )
    assert "'a.b'" in transformed  # string literal untouched
    assert "a.b ==" not in transformed  # bare ref replaced


def test_var_age_with_dotted_name_string_arg():
    """End-to-end: var_age must receive the original variable name."""
    from app.core.state_cache import StateCache
    import asyncio

    cache = StateCache()

    async def setup():
        await cache.set("ov.f1.state", "normal",
                         source_topic=None, source_kind="test")

    asyncio.run(setup())

    r = evaluate(
        'ov.f1.state == "normal" AND var_age("ov.f1.state") < 600',
        {"ov.f1.state": "normal"},
        state_cache=cache,
    )
    assert r.ok, r.error
    assert r.value is True


def test_escaped_quote_inside_string_doesnt_unmask_early():
    """Strings with escaped quotes (\\\") should still mask correctly."""
    from app.core.eval import _substitute_dots
    transformed, _, _ = _substitute_dots(
        r'x.y == "has\"quote" AND z.w == 5',
        {"x.y": 'has"quote', "z.w": 5},
    )
    # Both bare refs should be replaced
    assert "x.y ==" not in transformed
    assert "z.w ==" not in transformed
    # String content preserved
    assert r'"has\"quote"' in transformed
