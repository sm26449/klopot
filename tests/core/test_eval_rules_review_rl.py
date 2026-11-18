"""Rules review 2026-11-18 (RL-01, RL-04 … RL-08): expression-language gaps
that made a rule silently wrong, or an absent input count as a broken rule."""
from __future__ import annotations

import pytest

from app.core.eval import (
    MISSING_INPUT_PREFIX,
    ExpressionError,
    display_names,
    evaluate,
    referenced_names,
    validate_expression,
)

# The production rule that stopped firing when regexes moved to RE2.
LOOKAHEAD = 'regex_match(peers.list, "(^|,)(?!192[.]168[.]88[.]235(,|$))[0-9]")'


# ── RL-01: a regex RE2 cannot run is an error, never a silent False ──

def test_a_literal_pattern_re2_cannot_run_is_refused_at_save():
    with pytest.raises(ExpressionError, match="lookahead"):
        validate_expression(LOOKAHEAD)


def test_a_stored_one_fails_its_evaluation_visibly():
    r = evaluate(LOOKAHEAD, {"peers.list": "192.168.88.235,10.0.0.5"})
    assert not r.ok and not r.missing_input and "not supported" in (r.error or "")


def test_a_pattern_from_a_variable_fails_at_run_time():
    r = evaluate("regex_match(x.s, x.pat)", {"x.s": "ab", "x.pat": "a(?=b)"})
    assert not r.ok and not r.missing_input and "not supported" in (r.error or "")


def test_a_valid_pattern_still_matches():
    assert evaluate('regex_match(x.s, "^ab")', {"x.s": "abc"}).value is True
    validate_expression('regex_match(x.s, "^ab")')


# ── RL-04: the editor's variable list ───────────────────────────────

def test_display_names_skip_string_contents_but_keep_var_age_arguments():
    expr = 'contains(upper(sms.body), "STATUS") and var_age("a.b") < 30 and temp > x.y'
    assert display_names(expr) == ["sms.body", "a.b", "temp", "x.y"]


def test_keywords_are_never_variables():
    assert referenced_names("x > 1 and true or null == None") == frozenset({"x"})


# ── RL-05 / RL-06: an absent input waits for data, with or without dots ─

@pytest.mark.parametrize(("expr", "ctx", "waiting"), [
    ("temp > 5", {}, ["temp"]),                                   # undotted, absent
    ("a.b > 5", {"a.b": None}, ["a.b"]),                          # present, no value
    ('lower(a.b) == "x"', {"a.b": None}, ["a.b"]),
    ("len(a.b) > 3", {"a.b": None}, ["a.b"]),
])
def test_an_absent_input_is_no_data_not_an_error(expr, ctx, waiting):
    r = evaluate(expr, ctx)
    assert not r.ok and r.missing_input and r.missing_vars == waiting
    assert (r.error or "").startswith(MISSING_INPUT_PREFIX)


def test_an_unknown_function_is_still_an_error():
    r = evaluate("nope(1) > 0", {})
    assert not r.ok and not r.missing_input


def test_a_type_error_on_real_values_is_still_an_error():
    r = evaluate('a.b > "x"', {"a.b": 5})
    assert not r.ok and not r.missing_input


# ── RL-07: avg of nothing ──────────────────────────────────────────

def test_avg_of_missing_inputs_waits_for_data_instead_of_returning_zero():
    r = evaluate("avg([a.b, c.d]) < 5", {})
    assert not r.ok and r.missing_input


def test_avg_of_a_literal_empty_list_is_an_error():
    r = evaluate("avg([]) < 5", {})
    assert not r.ok and not r.missing_input and "no values" in (r.error or "")


def test_avg_ignores_none_values():
    assert evaluate("avg([a.b, c.d])", {"a.b": 4, "c.d": None}).value == 4.0


# ── RL-08: true / false / null are literals ─────────────────────────

@pytest.mark.parametrize(("expr", "value"), [
    ("true", True), ("TRUE", True), ("false", False), ("False", False),
    ("null == None", True), ("NULL == None", True), ("none == None", True),
    ("x.on == true", True),
])
def test_lowercase_and_uppercase_literals(expr, value):
    r = evaluate(expr, {"x.on": True})
    assert r.ok and r.value is value
