"""Rules review, stage 2 (RL-20 … RL-27): new expression functions."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core import eval as eval_module
from app.core.eval import ExpressionError, evaluate, validate_expression
from app.utils.sun import SUNRISE_ELEVATION, sun_elevation


class _Snap:
    def __init__(self, value, age, stale=False):
        self.value, self._age, self._stale = value, age, stale

    def age_sec(self) -> float:
        return self._age

    def is_stale(self) -> bool:
        return self._stale


class _Cache:
    def __init__(self, **snaps):
        self._snaps = {k.replace("__", "."): v for k, v in snaps.items()}

    def get(self, name):
        return self._snaps.get(name)


def _at(monkeypatch, when: datetime) -> None:
    """Freeze the evaluator's clock at ``when`` (an aware datetime)."""
    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.astimezone(tz) if tz else when
    monkeypatch.setattr(eval_module, "datetime", _Clock)


def _ev(expr, ctx=None, **kw):
    return evaluate(expr, ctx or {}, **kw)


# ── RL-20 fresh() ────────────────────────────────────────────────


def test_fresh_is_var_age_below_a_limit():
    cache = _Cache(pv__f1=_Snap(7, 30), pv__f2=_Snap(7, 500))
    assert _ev('fresh("pv.f1", 120)', state_cache=cache).value is True
    assert _ev('fresh("pv.f2", 120)', state_cache=cache).value is False
    assert _ev('fresh("pv.none", 120)', state_cache=cache).value is False


def test_fresh_and_has_arguments_are_shown_as_variables():
    assert eval_module.display_names('fresh("pv.f1", 120) AND has("b.c") AND x > 1') == ["pv.f1", "b.c", "x"]


# ── RL-21 has(), coalesce() ──────────────────────────────────────


def test_has_needs_a_value_that_is_not_stale():
    cache = _Cache(a=_Snap(1, 5), b=_Snap(1, 5, stale=True), c=_Snap(None, 5))
    assert [_ev(f'has("{n}")', state_cache=cache).value for n in "abcd"] == [True, False, False, False]


def test_coalesce_falls_back_on_a_missing_input():
    r = _ev("coalesce(battery.soc, 50) < 20", {})
    assert r.ok
    assert r.value is False
    assert r.missing_vars == ["battery.soc"]
    assert _ev("coalesce(battery.soc, 50)", {"battery.soc": 12}).value == 12
    assert _ev("coalesce(null, none, 3)").value == 3


# ── RL-22 between() ──────────────────────────────────────────────


@pytest.mark.parametrize(("x", "expected"), [(10, True), (5, True), (20, True), (4.9, False), (21, False)])
def test_between_is_inclusive(x, expected):
    assert _ev("between(x, 5, 20)", {"x": x}).value is expected


def test_between_of_a_missing_input_waits_for_data():
    r = _ev("between(battery.soc, 5, 20)", {})
    assert not r.ok
    assert r.missing_input


# ── RL-23 any(), all() ───────────────────────────────────────────


def test_any_and_all_over_a_list():
    ctx = {"pv.f1": 4, "pv.f2": 7, "pv.f3": 4}
    assert _ev("any([pv.f1 == 7, pv.f2 == 7, pv.f3 == 7])", ctx).value is True
    assert _ev("all([pv.f1 == 4, pv.f2 == 4, pv.f3 == 4])", ctx).value is False
    assert _ev("all([pv.f1 == 4, pv.f3 == 4])", ctx).value is True


def test_any_needs_a_list():
    r = _ev("any(5)")
    assert not r.ok
    assert "takes a list" in r.error


# ── RL-24 time: in_window with minutes, month_now, is_weekend ────


@pytest.mark.parametrize(("hhmm", "expected"), [
    ("22:29", False), ("22:30", True), ("23:59", True), ("00:00", True),
    ("06:14", True), ("06:15", False), ("12:00", False),
])
def test_in_window_with_minutes_crosses_midnight(monkeypatch, hhmm, expected):
    h, m = map(int, hhmm.split(":"))
    _at(monkeypatch, datetime(2026, 11, 18, h, m, tzinfo=UTC))
    assert _ev('in_window("22:30", "06:15")').value is expected


def test_in_window_hours_keep_their_meaning(monkeypatch):
    _at(monkeypatch, datetime(2026, 11, 18, 8, 0, tzinfo=UTC))
    assert _ev("in_window(8, 20)").value is True
    assert _ev("in_window(9, 20)").value is False
    assert _ev('in_window(7.5, "08:01")').value is True


@pytest.mark.parametrize("bad", ['"25:00"', '"8h"', '"08:60"', "-1", "25", "true"])
def test_in_window_refuses_a_bad_time(bad):
    r = _ev(f"in_window({bad}, 6)")
    assert not r.ok
    assert "in_window()" in r.error


def test_in_window_uses_the_timezone(monkeypatch):
    _at(monkeypatch, datetime(2026, 11, 18, 21, 30, tzinfo=UTC))   # 23:30 in Bucharest
    assert _ev('in_window("23:00", "23:59")', timezone="Europe/Bucharest").value is True
    assert _ev('in_window("23:00", "23:59")').value is False


def test_month_now_and_is_weekend(monkeypatch):
    _at(monkeypatch, datetime(2026, 11, 21, 12, 0, tzinfo=UTC))    # a Saturday
    assert _ev("month_now() == 11 AND is_weekend()").value is True
    _at(monkeypatch, datetime(2026, 11, 23, 12, 0, tzinfo=UTC))    # Monday
    assert _ev("is_weekend()").value is False


# ── RL-25 sun ────────────────────────────────────────────────────

BUCHAREST = (44.43, 26.10)


def test_sun_elevation_known_values():
    # Equator, March equinox, solar noon at Greenwich: the sun is overhead.
    assert sun_elevation(0, 0, datetime(2026, 3, 20, 12, 7, tzinfo=UTC)) > 89
    # Bucharest, summer solstice: noon about 69°, midnight well below.
    assert 68 < sun_elevation(*BUCHAREST, datetime(2026, 6, 21, 10, 15, tzinfo=UTC)) < 70
    assert sun_elevation(*BUCHAREST, datetime(2026, 6, 21, 22, 0, tzinfo=UTC)) < -15


def test_sunrise_in_bucharest_is_within_minutes_of_the_almanac():
    # 2026-06-21 sunrise 05:31 EEST = 02:31 UTC.
    assert sun_elevation(*BUCHAREST, datetime(2026, 6, 21, 2, 27, tzinfo=UTC)) < SUNRISE_ELEVATION
    assert sun_elevation(*BUCHAREST, datetime(2026, 6, 21, 2, 35, tzinfo=UTC)) > SUNRISE_ELEVATION


def test_is_daylight_follows_the_sun(monkeypatch):
    _at(monkeypatch, datetime(2026, 12, 21, 16, 0, tzinfo=UTC))    # 18:00 local, dark
    assert _ev("is_daylight()", location=BUCHAREST).value is False
    _at(monkeypatch, datetime(2026, 6, 21, 16, 0, tzinfo=UTC))     # 19:00 local, sun up
    assert _ev("is_daylight() AND sun_elevation() > 5", location=BUCHAREST).value is True


def test_sun_without_a_place_is_a_clear_error():
    r = _ev("is_daylight()")
    assert not r.ok
    assert not r.missing_input
    assert "ALERTD_LATITUDE" in r.error


def test_settings_location_needs_both_coordinates():
    from app.config import Settings
    assert Settings(latitude="44.4", longitude="26.1").location == (44.4, 26.1)
    assert Settings(latitude="44.4", longitude="").location is None
    with pytest.raises(ValueError, match="less than or equal to 90"):
        Settings(latitude="91")


# ── RL-26 unknown function refused when saved ────────────────────


def test_an_unknown_function_is_refused_at_write_time():
    with pytest.raises(ExpressionError, match=r"unknown function: fersh\(\)"):
        validate_expression('fersh("pv.f1", 120)')
    validate_expression('fresh("pv.f1", 120) AND between(x, 1, 2) AND any([a, b])')


def test_every_documented_function_exists():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "docs/EXPRESSION_LANGUAGE.md").read_text(encoding="utf-8")
    # Built into simpleeval's compound types, not part of the language.
    undocumented = {"dict", "list", "set", "tuple"}
    missing = sorted(n for n in eval_module.FUNCTION_NAMES - undocumented if f"`{n}(" not in text)
    assert not missing, f"document in docs/EXPRESSION_LANGUAGE.md: {missing}"


def test_the_editor_catalog_lists_every_function():
    """lib/expr.js drives the cheat-sheet and completion (RL-28)."""
    import re
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "app/admin_ui/static/lib/expr.js").read_text()
    listed = {n for group in re.findall(r'"rules\.cheat\w+",\s*\[([^\]]*)\]', js)
              for n in re.findall(r'"(\w+)"', group)}
    undocumented = {"dict", "list", "set", "tuple"}
    assert listed == eval_module.FUNCTION_NAMES - undocumented


# ── RL-27 computed variables use the install's timezone and place ──


@pytest.fixture
def bucharest_settings(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ALERTD_TZ", "Europe/Bucharest")
    monkeypatch.setenv("ALERTD_LATITUDE", "44.43")
    monkeypatch.setenv("ALERTD_LONGITUDE", "26.10")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_computed_formula_reads_the_local_hour_and_the_sun(monkeypatch, bucharest_settings):
    from app.core.state_cache import StateCache
    from app.core.variable_resolver import VariableResolver, VarMapping
    _at(monkeypatch, datetime(2026, 6, 21, 21, 30, tzinfo=UTC))     # 00:30 in Bucharest, dark
    cache = StateCache()
    resolver = VariableResolver(cache)
    resolver.replace_mappings([
        VarMapping(name="h", source="computed", value_type="number", formula="hour_now()"),
        VarMapping(name="day", source="computed", value_type="bool", formula="is_daylight()"),
    ])
    await resolver.recompute_computed()
    assert cache.value("h") == 0       # UTC would say 21
    assert cache.value("day") is False
