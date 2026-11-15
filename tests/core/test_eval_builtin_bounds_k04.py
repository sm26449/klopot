"""Whitelisted builtins cannot bypass the size bounds (review K04).

``sum`` is the builtin: ``sum(list_of_lists, [])`` concatenates inside one C
call that ``_bounded_mult`` / simpleeval's ``safe_add`` never see — 81 literals
of ``[0]*99999`` in an 824-character expression held the GIL ~4.5 s, through
``POST /v1/rules/validate`` with a ``read`` key. ``round(5, -9999999)`` makes
the builtin compute ``10 ** 9999999``: ~10 s, from a plain literal.
"""
from __future__ import annotations

import time

import pytest

from app.core.eval import evaluate

pytestmark = pytest.mark.anyio


def _fast(expr: str, ctx: dict | None = None):
    started = time.perf_counter()
    result = evaluate(expr, ctx or {})
    assert time.perf_counter() - started < 0.5, expr
    return result


def test_sum_of_lists_is_refused():
    bomb = "len(sum([" + ", ".join(["[0]*99999"] * 81) + "], [])) > 0"
    assert len(bomb) < 2000
    assert _fast(bomb).ok is False
    assert _fast("sum([[1], [2]], []) == [1, 2]").ok is False
    assert _fast("sum(['a', 'b'], '') == 'ab'").ok is False


def test_sum_of_numbers_still_works():
    assert evaluate("sum([1, 2, 3])", {}).value == 6
    assert evaluate("sum([1.5, 2], 10)", {}).value == 13.5
    assert evaluate("sum(xs) > 5", {"xs": [4, 3]}).value is True
    assert evaluate("sum([])", {}).value == 0


def test_round_with_a_huge_ndigits_is_refused():
    assert _fast("round(5, -9999999) > 0").ok is False
    assert _fast("round(5, 9999999) > 0").ok is False


def test_round_still_works():
    assert evaluate("round(2.567, 2)", {}).value == 2.57
    assert evaluate("round(1234, -2)", {}).value == 1200
    assert evaluate("round(2.5)", {}).value == 2


def test_many_bounded_products_together_are_refused():
    """Each ``[0]*99999`` passes the per-operation cap; their total must not."""
    many = "len([" + ", ".join(["[0]*99999"] * 81) + "]) > 0"
    assert _fast(many).ok is False
    chain = " + ".join(['len("a"*99999 + "b")'] * 20) + " > 0"
    result = _fast(chain)
    assert result.ok is False
    assert "too much data" in result.error
    assert evaluate("len([0]*1000 + [1]*1000) == 2000", {}).value is True
