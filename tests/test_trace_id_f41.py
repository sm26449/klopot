"""F41: an untrusted X-Trace-Id must be bounded so it can't overflow the
VARCHAR(40) trace_id columns and 500 the write."""
from __future__ import annotations

from app.logging_setup import _accept_trace


def test_wellformed_trace_is_kept():
    assert _accept_trace("abc-123_XYZ") == "abc-123_XYZ"
    assert _accept_trace("a" * 40) == "a" * 40  # exactly the column width


def test_oversized_trace_is_replaced_and_bounded():
    out = _accept_trace("a" * 200)
    assert out != "a" * 200
    assert len(out) <= 40


def test_malformed_trace_is_replaced():
    for bad in ["has spaces", "weird;chars", "../path", "a" * 41]:
        out = _accept_trace(bad)
        assert out != bad
        assert len(out) <= 40


def test_missing_trace_is_minted():
    out = _accept_trace(None)
    assert out
    assert len(out) <= 40
