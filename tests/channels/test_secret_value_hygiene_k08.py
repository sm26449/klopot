"""A resolved secret never carries whitespace or control characters (review K08).

A token from ``secrets.env`` with a trailing space, CR or a quoted ``\\n`` is
invalid in an HTTP header: h11 refused the request and quoted the header —
token included — in its error, which was stored on the delivery and in the
activity log (``read`` scope). Surrounding whitespace is trimmed; a value with
a control character inside is refused (the send fails as "missing secret").
"""
from __future__ import annotations

import pytest

from app.channels._secrets import resolve_secret
from app.inputs._secrets_helper import resolve_secret_local


@pytest.mark.parametrize("resolve", [resolve_secret, resolve_secret_local])
def test_surrounding_whitespace_is_trimmed(resolve, monkeypatch):
    monkeypatch.setenv("KLOPOT_SECRET_K08", "tok-123 \r\n")
    assert resolve({"t_ref": "KLOPOT_SECRET_K08"}, "t", "t_ref") == "tok-123"
    assert resolve({"t": "  literal\n"}, "t", "t_ref") == "literal"


@pytest.mark.parametrize("resolve", [resolve_secret, resolve_secret_local])
def test_a_control_character_inside_is_refused(resolve, monkeypatch):
    monkeypatch.setenv("KLOPOT_SECRET_K08", "tok\n123")
    assert resolve({"t_ref": "KLOPOT_SECRET_K08"}, "t", "t_ref") is None
    assert resolve({"t": "a\x00b"}, "t", "t_ref") is None
    assert resolve({"t": "   "}, "t", "t_ref") is None
