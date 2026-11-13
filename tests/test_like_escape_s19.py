"""S-19: a search term's LIKE metacharacters must be escaped so `%`/`_` match
literally instead of acting as wildcards (over-matching + slow-scan risk)."""
from __future__ import annotations

from app.utils.like import like_escape


def test_escapes_percent_and_underscore():
    assert like_escape("a%b") == "a\\%b"
    assert like_escape("a_b") == "a\\_b"


def test_escapes_backslash_first():
    # The escape char itself must be escaped, before % and _, so it can't form
    # an unintended escape sequence.
    assert like_escape("a\\b") == "a\\\\b"
    assert like_escape("100%_x\\") == "100\\%\\_x\\\\"


def test_plain_text_unchanged():
    assert like_escape("battery low") == "battery low"
