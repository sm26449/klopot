"""Pure-unit tests for app.core.rendering — no DB, no I/O."""
from __future__ import annotations

import pytest

from app.core.rendering import render


def test_returns_empty_for_none_or_empty():
    assert render(None, {}) == ""
    assert render("", {"x": 1}) == ""


def test_brace_substitution_simple():
    assert render("hello {name}", {"name": "world"}) == "hello world"


def test_percent_substitution_simple():
    assert render("hello %name%", {"name": "world"}) == "hello world"


def test_dotted_lookup():
    ctx = {"battery": {"soc": 42}}
    assert render("SOC: {battery.soc}", ctx) == "SOC: 42"


def test_flat_dotted_key_takes_precedence():
    """If the ctx has a literal dotted key, it wins over traversal —
    state-cache vars (e.g. ``battery.soc``) commonly arrive as flat
    keys."""
    ctx = {"battery.soc": 50, "battery": {"soc": 99}}
    assert render("{battery.soc}", ctx) == "50"


def test_missing_variable_renders_marker():
    assert render("hi {missing}", {}) == "hi [?missing]"


def test_int_floats_lose_decimal():
    assert render("{x}", {"x": 5.0}) == "5"


def test_non_int_floats_use_general_format():
    assert render("{x}", {"x": 5.25}) == "5.25"


def test_filter_round():
    assert render("{x | round(1)}", {"x": 3.456}) == "3.5"


def test_filter_kw_converts_w_to_kw():
    assert render("{p | kw} kW", {"p": 12340}) == "12.3 kW"


def test_filter_pct_rounds_to_int():
    assert render("{r | pct}", {"r": 84.6}) == "85"


def test_filter_div_with_arg():
    # 9000 / 1000 = 9.0 → trimmed to "9"
    assert render("{w | div(1000)}", {"w": 9000}) == "9"


def test_filter_chain():
    # round(2) then divide by 10 — pick a value with clean float repr
    assert render("{x | round(1) | div(10)}", {"x": 25.4}) == "2.54"


def test_unknown_filter_yields_marker():
    assert render("{x | doesnotexist}", {"x": 1}) == "[?x|doesnotexist]"


def test_multiple_placeholders():
    out = render(
        "PV {pv | kw} kW, SOC {soc}%",
        {"pv": 25500, "soc": 87},
    )
    assert out == "PV 25.5 kW, SOC 87%"


def test_lower_upper_filters():
    assert render("{s | upper}", {"s": "warning"}) == "WARNING"
    assert render("{s | lower}", {"s": "WARN"}) == "warn"


def test_fixed_filter():
    assert render("{x | fixed(2)}", {"x": 3.4567}) == "3.46"


def test_json_filter():
    out = render("payload={d | json}", {"d": {"k": 1}})
    assert out == 'payload={"k": 1}'


def test_jsonstr_filter_escapes_without_surrounding_quotes():
    # jsonstr escapes the inner content and does NOT add quotes, so it can
    # be embedded inside a JSON string literal (audit A18).
    out = render('{x | jsonstr}', {"x": 'he said "hi"\nbye'})
    assert out == 'he said \\"hi\\"\\nbye'


def test_jsonstr_embedded_in_json_template_stays_valid():
    import json as _json

    tmpl = '{"text": "**{title | jsonstr}**"}'
    rendered = render(tmpl, {"title": 'Grid "down"\nnow'})
    # Rendered output must parse as JSON and preserve the embedded text.
    assert _json.loads(rendered) == {"text": '**Grid "down"\nnow**'}


def test_no_substitution_when_no_placeholders():
    assert render("plain text", {"a": 1}) == "plain text"


def test_brace_with_whitespace_around_name():
    assert render("{ x }", {"x": 5}) == "5"


def test_div_missing_arg_yields_marker():
    assert render("{x | div}", {"x": 10}) == "[?x|div]"


# ── P0-4: re-expansion and unbounded precision ─────────────────────────

def test_context_value_is_not_re_expanded_as_template():
    # A resolved value that happens to look like another placeholder must be
    # inserted literally, never re-scanned as template (audit P0-4).
    assert render("Alert: {msg}", {"msg": "%other%", "other": "OTHER"}) == "Alert: %other%"
    assert render("%a%", {"a": "{b}", "b": "X"}) == "{b}"


def test_fixed_filter_precision_is_capped():
    # fixed(5000000) would format a number into a 5 MB string.
    out = render("%n|fixed(5000000)%", {"n": "1"})
    assert len(out) < 50
    assert out.startswith("1.")


def test_round_filter_precision_is_capped():
    assert render("{x|round(9999999)}", {"x": 3.14159}) == "3.14159"


def test_rendered_output_is_length_capped():
    # Even a pathological template can't push output past the safety cap.
    out = render("%n|fixed(12)%" * 20000, {"n": "1"})
    assert len(out) <= 100000
