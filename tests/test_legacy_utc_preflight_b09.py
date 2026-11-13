"""B-09: read-only legacy-UTC preflight exit-code logic and wiring.

The repair engines themselves (R09 0004/0005, B-13 config) are tested in
``test_historical_utc_r09.py`` and ``test_config_timestamp_repair_b13.py``.
Here we pin the preflight's verdict logic and that it is wired to both
repair tools' definitions.
"""
from __future__ import annotations

from scripts.check_legacy_utc import (
    B13_MARKER,
    R09_MARKER,
    R09_TABLES,
    DomainResult,
    decide_exit,
)
from scripts.correct_config_timestamps_b13 import target_columns


def _r(label, assessed, marked, suspect):
    return DomainResult(label=label, assessed=assessed, marked=marked, suspect=suspect)


# ── Exit-code verdict ────────────────────────────────────────────────


def test_no_domains_is_ok():
    assert decide_exit([]) == 0


def test_all_clean_is_ok():
    assert decide_exit([_r("a", True, False, 0), _r("b", True, True, 0)]) == 0


def test_marked_domain_never_triggers_action():
    # A marker means already corrected: suspect count is ignored.
    assert decide_exit([_r("a", True, True, 5)]) == 0


def test_unassessed_domain_never_triggers_action():
    # No cutoff given -> can't judge -> must not claim action needed.
    assert decide_exit([_r("config timestamps", False, False, 0)]) == 0


def test_assessed_unmarked_suspect_rows_need_action():
    assert decide_exit([_r("audit_log.ts", True, False, 3)]) == 2


def test_action_when_any_domain_needs_it():
    results = [
        _r("audit_log.ts", True, True, 0),          # corrected
        _r("notifications_log.fired_at", True, False, 0),  # clean
        _r("config timestamps", True, False, 7),    # needs action
    ]
    assert decide_exit(results) == 2


# ── Wiring to both repair tools ──────────────────────────────────────


def test_preflight_covers_both_log_tables():
    names = {(s.table, s.column) for s in R09_TABLES}
    assert names == {("audit_log", "ts"), ("notifications_log", "fired_at")}


def test_preflight_covers_config_columns():
    assert len(target_columns()) > 0


def test_markers_are_distinct():
    assert R09_MARKER != B13_MARKER
    assert R09_MARKER == "historical_utc_corrected"
    assert B13_MARKER == "config_timestamps_utc_corrected"
