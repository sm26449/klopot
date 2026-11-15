"""V20: forward-only downgrade guard — a downgrade is refused as a global
preflight before any step runs, unless the operator explicitly opts in."""
from __future__ import annotations

import pytest

from app.db.migration_guard import (
    assert_no_unapproved_downgrade,
    downgrade_allowed,
)


class _Step:
    def __init__(self, is_downgrade: bool) -> None:
        self.is_downgrade = is_downgrade


def test_downgrade_allowed_reads_override(monkeypatch):
    monkeypatch.delenv("ALERTD_ALLOW_DOWNGRADE", raising=False)
    assert downgrade_allowed() is False
    for val in ("1", "true", "YES", "on"):
        monkeypatch.setenv("ALERTD_ALLOW_DOWNGRADE", val)
        assert downgrade_allowed() is True
    monkeypatch.setenv("ALERTD_ALLOW_DOWNGRADE", "0")
    assert downgrade_allowed() is False


def test_upgrade_only_steps_pass(monkeypatch):
    monkeypatch.delenv("ALERTD_ALLOW_DOWNGRADE", raising=False)
    # No exception: an upgrade (or a stamp with no steps) is never blocked.
    assert_no_unapproved_downgrade([_Step(False), _Step(False)])
    assert_no_unapproved_downgrade([])


def test_downgrade_refused_without_override(monkeypatch):
    monkeypatch.delenv("ALERTD_ALLOW_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="forward-only"):
        assert_no_unapproved_downgrade([_Step(False), _Step(True)])


def test_downgrade_allowed_with_override(monkeypatch):
    monkeypatch.setenv("ALERTD_ALLOW_DOWNGRADE", "1")
    # Explicit opt-in → the preflight lets the downgrade through.
    assert_no_unapproved_downgrade([_Step(True)])
