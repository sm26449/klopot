"""B-07: uppercase AND/OR/NOT normalization must only touch language tokens,
never the contents of a quoted string literal.

Before the fix, the evaluator rewrote AND/OR/NOT everywhere before masking
strings, so a literal like ``"NOT ready"`` became ``"not ready"`` and a valid
comparison against the real text ``NOT ready`` silently evaluated false — a
legitimate alert could stay absent with no error. The fix masks string literals
first, so keyword normalization is confined to tokens outside quotes.
"""
from __future__ import annotations

import pytest

from app.core.eval import evaluate

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("literal", [
    "NOT ready",
    "Moderate OR high",
    "AND gate",
    "not lower",          # already-lowercase keyword inside a string
    "run OR reassert",
    "state is NOT normal",
])
async def test_keyword_inside_string_literal_is_preserved(literal):
    # Double-quoted
    assert evaluate(f'x == "{literal}"', {"x": literal}).value is True
    # Single-quoted
    assert evaluate(f"x == '{literal}'", {"x": literal}).value is True


async def test_keyword_normalization_outside_strings_still_works():
    assert evaluate("a AND b", {"a": True, "b": True}).value is True
    assert evaluate("a OR b", {"a": False, "b": True}).value is True
    assert evaluate("NOT a", {"a": False}).value is True
    assert evaluate("a AND NOT b", {"a": True, "b": False}).value is True


async def test_mixed_token_and_literal():
    """The outer AND is normalized while the string literal keeps its text."""
    r = evaluate('a AND label == "NOT x"', {"a": True, "label": "NOT x"})
    assert r.value is True
    r2 = evaluate('a AND label == "NOT x"', {"a": True, "label": "not x"})
    assert r2.value is False      # 'not x' != 'NOT x' — case is preserved, not normalized


async def test_dotted_name_inside_string_still_survives():
    """The masking that fixes B-07 is the same masking that protects dotted
    names inside strings — keep that working too."""
    # var_age needs a state cache; without one the call errors, but the point is
    # the literal 'ov.f1.state' must reach var_age intact, not be rewritten.
    from app.core.eval import _substitute_dots
    transformed, _, _ = _substitute_dots('var_age("ov.f1.state") < 600', {})
    assert '"ov.f1.state"' in transformed       # literal untouched
    assert "var_age" in transformed
