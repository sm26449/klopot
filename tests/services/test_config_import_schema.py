"""Unit tests for the config-import pack contract (audit A09).

These exercise ``validate_pack`` directly (no DB): every input that used
to raise and surface as a 500 must now come back as a localized error
string, and a well-formed pack must validate clean.
"""
from __future__ import annotations

from app.services.config_import_schema import validate_pack


def _errs(cfg):
    return validate_pack(cfg)


def test_valid_pack_passes_clean():
    cfg = {
        "version": "1.0",
        "settings": {"timezone": "Europe/Bucharest", "log_retention_days": 30},
        "inputs": [{"name": "ekrano", "kind": "mqtt", "config": {"host": "x"}}],
        "templates": [{"type": "t1", "severity": "warning", "title_template": "hi"}],
        "channels": [{"name": "ui_default", "kind": "ui"}],
        "variables": [{"name": "soc", "source": "mqtt", "input": "ekrano",
                       "config": {"topic": "s/soc"}}],
        "rules": [{"name": "r1", "template_type": "t1", "condition_expr": "soc < 20"}],
        "routes": [{"template": "t1", "channel": "ui_default", "severity_min": "info"}],
        "schedules": [{"name": "s1", "cron_expr": "0 0 * * *", "template_type": "t1"}],
    }
    assert _errs(cfg) == []


def test_section_as_scalar_is_rejected():
    # `inputs: 5` used to crash the cross-ref loop with TypeError → 500.
    errs = _errs({"inputs": 5})
    assert errs
    assert any("inputs" in e for e in errs)


def test_invalid_channel_kind_is_rejected():
    errs = _errs({"channels": [{"name": "c", "kind": "carrier_pigeon"}]})
    assert errs
    assert any("kind" in e.lower() for e in errs)


def test_template_missing_title_is_rejected():
    errs = _errs({"templates": [{"type": "t", "severity": "info"}]})
    assert errs
    assert any("title_template" in e for e in errs)


def test_settings_unknown_key_id_is_rejected():
    # The headline A09 repro: `settings: {id: 2}` was "declared valid" and
    # would setattr the primary key. Now forbidden.
    errs = _errs({"settings": {"id": 2}})
    assert errs
    assert any("settings" in e and "id" in e for e in errs)


def test_duplicate_identifier_in_pack_is_rejected():
    errs = _errs({"inputs": [
        {"name": "dup", "kind": "mqtt"},
        {"name": "dup", "kind": "mqtt"},
    ]})
    assert errs
    assert any("duplicate" in e.lower() and "dup" in e for e in errs)


def test_over_length_name_is_rejected():
    errs = _errs({"inputs": [{"name": "x" * 65, "kind": "mqtt"}]})
    assert errs
    assert any("name" in e for e in errs)


def test_missing_required_enum_source_is_rejected():
    errs = _errs({"variables": [{"name": "v"}]})
    assert errs
    assert any("source" in e for e in errs)


def test_invalid_rule_missing_condition_is_rejected():
    errs = _errs({"rules": [{"name": "r", "template_type": "t"}]})
    assert errs
    assert any("condition_expr" in e for e in errs)


def test_errors_are_localized_with_path():
    errs = _errs({"templates": [{"type": "t", "severity": "info"}]})
    # Path should point at the offending field within the section/index.
    assert any(e.startswith("templates.0.") for e in errs), errs
