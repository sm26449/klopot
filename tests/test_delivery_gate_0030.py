"""Migration 0030: the solar-specific ``require_pv_kw`` + global
ALERTD_PV_POWER_VAR became a per-template delivery gate (``gate_variable`` +
``gate_min``). /v1 keeps ``require_pv_kw`` as a deprecated alias so existing
clients keep working."""
from __future__ import annotations

import contextlib
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.template import TemplateCreate, TemplateRead, TemplateUpdate
from app.services.config_io import legacy_template_gate


@contextlib.contextmanager
def _legacy_var(name: str):
    settings = get_settings()
    old = settings.pv_power_var
    object.__setattr__(settings, "pv_power_var", name)
    try:
        yield
    finally:
        object.__setattr__(settings, "pv_power_var", old)


def test_new_fields_round_trip():
    t = TemplateCreate(type="t", severity="info", title_template="x", gate_variable="tank.level", gate_min=20)
    assert (t.gate_variable, t.gate_min) == ("tank.level", 20)


def test_gate_variable_must_be_a_variable_name():
    with pytest.raises(ValidationError):
        TemplateCreate(type="t", severity="info", title_template="x", gate_variable="bad name!")


def test_legacy_alias_on_create_fills_gate_from_old_setting():
    with _legacy_var("pv.kw"):
        t = TemplateCreate(type="t", severity="info", title_template="x", require_pv_kw=4.5)
    assert (t.gate_variable, t.gate_min) == ("pv.kw", 4.5)
    assert "require_pv_kw" not in t.model_dump(exclude={"require_pv_kw"})


def test_legacy_alias_on_patch_is_a_change_to_gate_min():
    with _legacy_var(""):
        u = TemplateUpdate(require_pv_kw=3)
    changes = u.model_dump(exclude_unset=True, exclude={"require_pv_kw"})
    assert changes == {"gate_min": 3}  # no variable configured → none invented


def test_explicit_gate_fields_win_over_the_alias():
    with _legacy_var("pv.kw"):
        u = TemplateUpdate(require_pv_kw=3, gate_min=7, gate_variable="tank.level")
    assert (u.gate_variable, u.gate_min) == ("tank.level", 7)


def test_read_mirrors_gate_min_into_the_alias():
    now = datetime(2026, 11, 15)
    r = TemplateRead(id=1, type="t", severity="info", title_template="x", gate_variable="v", gate_min=2.5,
                     created_at=now, updated_at=now)
    assert r.require_pv_kw == 2.5


def test_import_maps_the_legacy_key_with_a_warning():
    with _legacy_var(""):
        item, warning = legacy_template_gate({"type": "t", "require_pv_kw": 4})
    assert item == {"type": "t", "gate_min": 4, "gate_variable": None}
    assert warning and "deprecated" in warning and "gate_variable" in warning
    same, none = legacy_template_gate({"type": "t", "gate_min": 4})
    assert none is None and same == {"type": "t", "gate_min": 4}
