"""P0-3: the expression sandbox must bound each operator's RESULT size, not only
the ``**`` exponent (A-01). A read/validate-scoped caller could otherwise burn
CPU or allocate gigabytes inline on the event loop — and a saved rule would
re-trigger it every tick, surviving a restart — via:

- ``%`` printf formatting on a string (``'%20000000d' % 1`` → 20 MB),
- ``*`` sequence repetition (``'x' * 10**9``, ``[[0]*n]*n`` then an n² compare),
- nested ``**`` (each exponent ≤ cap, but the base is already huge).

Every payload must evaluate False (rejected) in well under a second; legitimate
arithmetic must still work.
"""
from __future__ import annotations

import time

import pytest

from app.core.eval import evaluate

pytestmark = pytest.mark.anyio

_BOMBS = [
    "'%20000000d' % 1",                    # printf width → 20 MB string
    "'%1000000000d' % 1",                  # printf width → 1 GB string
    "(9**999)**999",                       # nested pow → multi-Mbit int
    "[[0]*3000]*3000 == [[0]*3000]*3000",  # n² list comparison
    "'x' * (10**9)",                       # string repetition → 1 GB
    "[0] * 100000000",                     # list repetition
    "10 ** 99999",                         # single pow, exponent over cap
]


@pytest.mark.parametrize("expr", _BOMBS)
async def test_resource_bomb_is_blocked_and_fast(expr):
    start = time.perf_counter()
    result = evaluate(expr, {"n": 1})
    elapsed = time.perf_counter() - start
    assert result.ok is False, f"{expr!r} should be rejected, got {result.value!r}"
    assert elapsed < 0.5, f"{expr!r} took {elapsed:.2f}s — operator size not bounded"


_ALLOWED = [
    ("10 ** 3", 1000),
    ("soc % 2", 0),
    ("'ab' * 3", "ababab"),
    ("2 * soc", 8),
    ("soc > 2 and soc < 10", True),
]


@pytest.mark.parametrize(("expr", "expected"), _ALLOWED)
async def test_legit_arithmetic_still_works(expr, expected):
    result = evaluate(expr, {"soc": 4})
    assert result.ok is True, result.error
    assert result.value == expected
