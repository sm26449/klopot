"""V10: user-supplied regexes run through RE2, so a catastrophic pattern can't
hold the GIL and freeze the event loop. Python's `re` backtracks exponentially
and never releases the GIL, so the earlier off-thread wall-clock budget could
not actually interrupt it — RE2 matches in linear time instead."""
from __future__ import annotations

import time

from app.core.eval import _regex_match


def test_catastrophic_regex_is_linear_time():
    """`(a+)+$` over a non-matching subject is O(2^n) under a backtracking
    engine but linear under RE2. Both pattern and subject are within the length
    caps, so the caps do not mask the attack — only the engine choice does."""
    pattern = r"(a+)+$"
    subject = "a" * 24 + "!"   # no trailing anchor match → full backtrack on `re`

    start = time.perf_counter()
    result = _regex_match(subject, pattern)
    elapsed = time.perf_counter() - start

    assert result is False
    # RE2 settles this in well under a millisecond; a backtracking engine takes
    # seconds here. A generous bound still cleanly separates the two.
    assert elapsed < 0.5, f"regex took {elapsed:.3f}s — backtracking not bounded"


def test_unsupported_regex_syntax_fails_closed():
    """RE2 cannot represent lookahead or backreferences. Rather than fall back
    to a backtracking engine, such a pattern fails closed — no match, no crash,
    no exception leaking to the caller."""
    assert _regex_match("foobar", r"foo(?=bar)") is False   # lookahead
    assert _regex_match("aa", r"(a)\1") is False            # backreference


def test_supported_regex_still_matches():
    """Ordinary patterns keep working under RE2."""
    assert _regex_match("plcbus/inverter/1", r"plcbus/.*/\d+") is True
    assert _regex_match("tankbus/pack", r"plcbus/.*") is False
    assert _regex_match("WARNING: soc low", r"^WARN") is True
