"""A missing dotted variable binds to None — the age guard short-circuits
and no NameError is counted (the inverters' namespace vanishes at sunset)."""
from __future__ import annotations

from app.core.eval import _substitute_dots, evaluate


def test_missing_dotted_names_bind_to_none_and_are_reported():
    expr, ctx, missing = _substitute_dots('inverter.max_voltage_l1 > 253 and pv.total_w > 0', {'pv.total_w': 5.0})
    assert missing == ['inverter.max_voltage_l1']
    assert 'inverter.max_voltage_l1' not in expr and ctx['__v1__'] == 5.0 and ctx['__v0__'] is None


def test_the_age_guard_short_circuits_a_stale_namespace():
    class _Snap:
        def age_sec(self): return 1e9
    class _Cache:
        def get(self, name): return None          # never seen → var_age inf
    r = evaluate('var_age("inverter.max_voltage_l1") < 120 and inverter.max_voltage_l1 > 253', {}, state_cache=_Cache())
    assert r.ok and r.value is False and r.missing_vars == ['inverter.max_voltage_l1']


def test_a_bare_comparison_with_a_missing_name_is_a_missing_input_not_an_error():
    r = evaluate('inverter.max_voltage_l1 > 253', {})
    assert not r.ok and r.missing_input and r.missing_vars == ['inverter.max_voltage_l1']
    assert (r.error or '').startswith('missing input: inverter.max_voltage_l1')


def test_a_type_error_without_a_missing_name_is_still_an_error():
    r = evaluate('pv.total_w > "x"', {'pv.total_w': 5.0})
    assert not r.ok and not r.missing_input and 'TypeError' in (r.error or '')
