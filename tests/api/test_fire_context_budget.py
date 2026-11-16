"""POST /v1/fire bounds its `context` (public-exposure review, Codex #3):
size as compact JSON (ALERTD_FIRE_CONTEXT_MAX_BYTES, default 16 KiB) and
nesting depth (16). Only the 1 MiB request cap bounded it, and an unknown
type still stored it."""
from __future__ import annotations

import pytest

from app.utils.context_budget import MAX_DEPTH, check_context, context_bytes, context_depth


def _nested(levels: int) -> dict:
    value: dict = {"leaf": 1}
    for _ in range(levels - 1):
        value = {"n": value}
    return value


def test_size_is_the_compact_utf8_json():
    assert context_bytes({"a": "ă"}) == len('{"a":"ă"}'.encode())
    # A lone surrogate is accepted and stored as U+FFFD (3 bytes): measured, not refused.
    assert context_bytes({"a": "\ud800"}) == len('{"a":"\ufffd"}'.encode())
    assert context_depth({}) == 1
    assert context_depth({"a": 1}) == 1
    assert context_depth({"a": [1, {"b": 2}]}) == 3
    assert context_depth(_nested(5000)) == 5000, "iterative: no recursion limit"


def test_the_limits_name_themselves():
    check_context(_nested(MAX_DEPTH), max_bytes=10_000)
    with pytest.raises(ValueError, match=f"limit is {MAX_DEPTH}"):
        check_context(_nested(MAX_DEPTH + 1), max_bytes=10_000)
    with pytest.raises(ValueError, match="ALERTD_FIRE_CONTEXT_MAX_BYTES"):
        check_context({"x": "y" * 2000}, max_bytes=1024)


async def test_the_api_refuses_an_oversized_or_too_deep_context(db_client, admin_key, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "fire_context_max_bytes", 1024)
    h = {"X-API-Key": admin_key}
    big = await db_client.post("/v1/fire", headers=h, json={"type": "t", "context": {"x": "y" * 2000}})
    deep = await db_client.post("/v1/fire", headers=h, json={"type": "t", "context": _nested(MAX_DEPTH + 1)})
    ok = await db_client.post("/v1/fire", headers=h, json={"type": "t", "context": {"x": "y" * 100}})
    assert big.status_code == 422
    assert "ALERTD_FIRE_CONTEXT_MAX_BYTES" in big.text
    assert deep.status_code == 422
    assert ok.status_code in (200, 202), ok.text
