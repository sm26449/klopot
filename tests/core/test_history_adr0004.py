"""ADR-0004: history functions in rule expressions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.core import history as history_module
from app.core.eval import ExpressionError, evaluate, make_evaluator, validate_expression
from app.core.history import HistoryStore, MissingHistory, Series, merge_needs, needs_of, parse_window


@dataclass
class Snap:
    ts: float
    value: Any
    stale: bool = False

    def is_stale(self) -> bool:
        return self.stale


# ── Parsing and write-time checks ──────────────────────────────────


@pytest.mark.parametrize(("text", "sec"), [("30s", 30), ("5m", 300), ("2h", 7200), ("1.5m", 90), ("24h", 86400)])
def test_parse_window(text, sec):
    assert parse_window(text) == sec


@pytest.mark.parametrize("text", ["25h", "0s", "5", "5d", "", 5])
def test_parse_window_refuses(text):
    with pytest.raises(ValueError, match="window"):
        parse_window(text)


@pytest.mark.parametrize(("expr", "why"), [
    ('avg_over(a.b, "5m") > 1', "in quotes"),
    ('delta("a", w) > 1', "in quotes"),
    ('avg_over("a", "25h") > 1', "between 1s and 24h"),
    ('prev("x", "5m") == 1', r'prev\("name"\)'),
])
def test_history_calls_need_literals(expr, why):
    with pytest.raises(ExpressionError, match=why):
        validate_expression(expr)


def test_needs_follow_the_ast_not_the_spelling():
    """RC-05: a space before the parenthesis passed validation but tracked nothing."""
    assert needs_of('avg_over ("sensor", "5m") > 40') == {"sensor": 300}
    assert needs_of('max_over(\n  "a", "1m") > 1 AND prev ( "b" ) == 2') == {"a": 60, "b": 0}


def test_needs_are_read_from_the_expressions():
    assert needs_of('avg_over("bat.t", "5m") > 40 AND delta("bat.t", "1h") < -3 AND prev("st") == 1') == {
        "bat.t": 3600, "st": 0}
    assert merge_needs(['max_over("a", "30s") > 1', None, 'changed("a", "2m")']) == {"a": 120}
    assert needs_of("a > 1") == {}


# ── The series ─────────────────────────────────────────────────────


def _series(window, points):
    s = Series(window=window)
    for t, v in points:
        s.add(t, v)
    return s


def test_the_average_is_weighted_by_time():
    s = _series(1000, [(0, 10), (5, 20)])
    assert s.avg("x", 10, now=10) == 15                 # 10 for 5 s, 20 for 5 s
    assert s.avg("x", 4, now=10) == 20                  # only the 20 level
    assert _series(1000, [(0, 10), (9, 20)]).avg("x", 10, now=10) == 11


def test_a_window_not_covered_yet_is_missing():
    s = _series(1000, [(0, 10)])
    with pytest.raises(MissingHistory, match="history 10s of 20s"):
        s.avg("x", 20, now=10)


def test_min_max_delta_rate():
    s = _series(1000, [(0, 10), (3, 25), (6, 5), (8, 20)])
    assert (s.extreme("x", 10, 10, min), s.extreme("x", 10, 10, max)) == (5, 25)
    assert s.delta("x", 10, now=10) == 10
    assert s.delta("x", 5, now=10) == -5                # level 25 at t=5 → 20


def test_every_change_is_kept_exactly():
    s = _series(2000, [(0, 1), (100, 5), (100.5, 9), (100.7, 7)])
    assert list(s.values) == [1, 5, 9, 7]
    assert s.extreme("x", 200, 200, max) == 9
    assert s.extreme("x", 200, 200, min) == 1


# rc.9 review RC-02: one variable watched for 24 h by one rule and for a minute
# by another — the merged buckets of the long window gave the short one wrong
# answers.

def test_a_short_window_on_a_long_tracked_variable_sees_the_peak():
    s = _series(86400, [(0, 0), (100, 1), (110, 100), (120, 1)])
    assert s.extreme("x", 60, 160, max) == 100


def test_a_short_window_sees_a_change_and_back():
    s = _series(86400, [(0, 0), (100, 1), (110, 2), (120, 1)])
    assert s.changed_in("x", 60, 160) is True


def test_the_average_weights_the_level_at_the_window_start():
    s = _series(86400, [(0, 0), (40, 100)])
    assert s.avg("x", 60, 60) == pytest.approx(100 / 3)


def test_past_the_point_budget_a_window_is_missing_not_approximate(monkeypatch):
    monkeypatch.setattr(history_module, "MAX_POINTS", 5)
    s = _series(1000, [(t, t % 2) for t in range(20)])
    assert len(s.times) == 5
    with pytest.raises(MissingHistory, match="the last 5 changes are kept"):
        s.avg("x", 10, 20)
    assert s.changed_in("x", 3, 20) is True


def test_changed_and_prev():
    s = _series(1000, [(0, "on")])
    assert s.changed_in("x", 10, now=10) is False
    s.add(12, "off")
    assert s.changed_in("x", 10, now=15) is True
    assert (s.prev, s.has_prev) == ("on", True)
    s.add(13, "off")                                    # same value: no new level
    assert s.prev == "on"


def test_text_in_a_numeric_function_is_missing():
    s = _series(1000, [(0, "x"), (5, 3)])
    with pytest.raises(MissingHistory, match="not a number"):
        s.avg("x", 10, now=10)


def test_old_points_are_dropped_but_the_level_at_the_start_is_kept():
    s = _series(10, [(t, t) for t in range(0, 100, 2)])
    assert s.times[0] <= 98 - 10 < s.times[1]
    assert s.avg("x", 10, now=100) == 94          # levels 90, 92 … 98, 2 s each


# ── The store and the evaluator ────────────────────────────────────


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 100.0}
    monkeypatch.setattr(history_module.time, "monotonic", lambda: now["t"])
    return now


async def test_store_tracks_only_what_is_needed(clock):
    store = HistoryStore()
    store.set_needs("rules", {"bat.t": 60})
    store.set_needs("computed", {"bat.t": 300, "x": 0})
    assert store.tracked() == {"bat.t": 300, "x": 0}
    await store._on_set("other", Snap(1, 5))
    assert "other" not in store.tracked()
    store.set_needs("computed", {})
    assert store.tracked() == {"bat.t": 60}


async def test_evaluate_with_history(clock):
    store = HistoryStore()
    store.set_needs("rules", {"bat.t": 600, "st": 0})
    for t, v in ((0, 40), (50, 50)):
        await store._on_set("bat.t", Snap(t, v))
    await store._on_set("st", Snap(1, 7))
    await store._on_set("st", Snap(2, 3))
    ev = make_evaluator(history=store)
    assert evaluate('avg_over("bat.t", "100s")', {}, evaluator=ev).value == 45
    assert evaluate('delta("bat.t", "1m") == 10', {}, evaluator=ev).value is True
    assert evaluate('prev("st") == 7 AND st != 7', {"st": 3}, evaluator=ev).value is True
    waiting = evaluate('avg_over("bat.t", "10m") > 1', {}, evaluator=ev)
    assert waiting.missing_input
    assert "history 100s of 10m" in waiting.error
    untracked = evaluate('avg_over("nope", "1m") > 1', {}, evaluator=ev)
    assert untracked.missing_input
    assert "not used by a saved, enabled rule" in untracked.error


async def test_a_stale_variable_has_no_history(clock):
    class Cache:
        def __init__(self):
            self.snap = Snap(0, 40)

        def get(self, name):
            return self.snap

        def subscribe(self, fn):
            return None
    cache = Cache()
    store = HistoryStore(cache)
    store.set_needs("rules", {"bat.t": 60})              # seeded from the cache's value
    assert store.series("bat.t").avg("bat.t", 60, 100) == 40
    cache.snap.stale = True
    with pytest.raises(MissingHistory, match="stale"):
        store.series("bat.t")


def test_the_variable_budget(clock):
    store = HistoryStore(max_vars=2)
    store.set_needs("rules", {"a": 60, "b": 60, "c": 60})
    assert sorted(store.tracked()) == ["a", "b"]
    with pytest.raises(MissingHistory, match="ALERTD_HISTORY_MAX_VARS"):
        store.series("c")


async def test_the_engine_reload_tells_the_store(db_engine, db_session, make_rule, make_template):
    from app.core.engine import RuleEngine
    from app.core.history import get_history_store
    t = make_template(type="h1", min_repeat_min=0)
    db_session.add_all([t, make_rule(template_type="h1", condition_expr='avg_over("bat.t", "5m") > 40',
                                     recovery_expr='max_over("bat.t", "15m") < 30', incident_enabled=True),
                        make_rule(name="off", template_type="h1", condition_expr='delta("z", "1h") > 1', enabled=False)])
    await db_session.commit()
    await RuleEngine().reload_rules()
    assert get_history_store().tracked() == {"bat.t": 900}



def test_a_cleared_value_takes_its_history_with_it(clock):
    """RC-04: the cache dropped x (an input rebound), the history kept answering."""
    from app.core.state_cache import StateCache
    cache = StateCache()
    store = HistoryStore(cache)
    store.set_needs("rules", {"x": 60})
    store._series["x"].add(0, 50)
    cache._values["x"] = Snap(0, 50)                    # a current value
    assert store.series("x").avg("x", 60, 100) == 50
    cache.clear(only={"x"})
    with pytest.raises(MissingHistory, match="no current value"):
        store.series("x")
    assert list(store._series["x"].values) == []


def test_a_new_need_never_evicts_a_tracked_one(clock):
    """RC-03: with the budget full, a new rule's variable used to push out an
    existing rule's (alphabetical order)."""
    store = HistoryStore(max_vars=1)
    store.set_needs("rules", {"z": 60})
    store.set_needs("rules", {"z": 60, "a": 60})
    assert store.tracked() == {"z": 60}
    assert store.dropped == ["a"]
