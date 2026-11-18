"""R08: a pathological regex in a read-scoped expression must not be able to
block the event loop. Inputs/patterns are length-bounded, and /rules/validate
evaluates off the loop under a wall-clock budget."""
from __future__ import annotations

import time

import pytest

from app.core.eval import _REGEX_MAX_PATTERN, _REGEX_MAX_SUBJECT, ExpressionError, _regex_match


def test_regex_match_normal_still_works():
    assert _regex_match("hello", "ell") is True
    assert _regex_match("hello", "xyz") is False
    assert _regex_match(None, "x") is False


def test_regex_match_oversized_pattern_refused():
    # Refused loudly, never a silent False (review RL-01).
    with pytest.raises(ExpressionError, match="too long"):
        _regex_match("a", "a" * (_REGEX_MAX_PATTERN + 1))


def test_regex_match_oversized_subject_refused():
    with pytest.raises(ExpressionError, match="subject too long"):
        _regex_match("a" * (_REGEX_MAX_SUBJECT + 1), "a")


async def test_validate_rejects_oversized_expression(db_client, admin_key):
    r = await db_client.post(
        "/v1/rules/validate",
        json={"condition_expr": "1" * 2001},
        headers={"X-API-Key": admin_key},
    )
    assert r.status_code == 422, r.text


async def test_validate_times_out_on_expensive_eval(db_client, admin_key, monkeypatch):
    import app.api.v1.rules as rules_mod

    monkeypatch.setattr(rules_mod, "_VALIDATE_EVAL_BUDGET_SEC", 0.05)

    def _slow_eval(expr, ctx, **kw):
        time.sleep(0.5)  # exceeds the budget; runs in a worker thread
        raise AssertionError("should have timed out")

    monkeypatch.setattr(rules_mod.eval_module, "evaluate", _slow_eval)

    r = await db_client.post(
        "/v1/rules/validate",
        json={"condition_expr": "soc < 20"},
        headers={"X-API-Key": admin_key},
    )
    assert r.status_code == 422, r.text
    assert "expensive" in r.text
