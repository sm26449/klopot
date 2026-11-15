"""The expression masker cannot be confused by the source text (review K20).

String literals are masked as ``\\x00S<n>\\x00`` before AND/OR/NOT and dotted
names are rewritten. A raw ``\\x00S5\\x00`` in the expression made the unmask
step index past its list: ``evaluate`` (which must never raise) raised
IndexError, a 500 from ``POST /v1/rules/validate`` (read scope). A triple-quoted
literal holding a quote (``\"\"\"a "AND" b\"\"\"``) was masked in pieces, so the
AND inside was rewritten and the rule compared against different text.
Control characters and triple-quoted literals are now refused.
"""
from __future__ import annotations

import pytest

from app.core.eval import ExpressionError, evaluate, validate_expression


@pytest.mark.parametrize("expr", ["\x00S5\x00 == 1", "x == 1\x00", "x\x07 == 1"])
def test_control_characters_are_refused_not_raised(expr):
    result = evaluate(expr, {"x": 1})
    assert result.ok is False
    assert "control character" in result.error
    with pytest.raises(ExpressionError):
        validate_expression(expr)


@pytest.mark.parametrize("expr", ['x == """a "AND" b"""', "x == '''a 'OR' b'''"])
def test_triple_quoted_literals_are_refused(expr):
    assert evaluate(expr, {"x": "a"}).ok is False
    with pytest.raises(ExpressionError):
        validate_expression(expr)


def test_ordinary_whitespace_and_quotes_still_work():
    assert evaluate("(x == 'a AND b'\n  and y > 1\t)", {"x": "a AND b", "y": 2}).value is True
    assert evaluate('x == "it\'s"', {"x": "it's"}).value is True
