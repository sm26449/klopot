"""Template DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from ..utils.icons import normalize_category, validate_icon
from .common import Severity
from .log import _as_utc_iso

# ── Delivery gate ───────────────────────────────────────────────────
# A template may be relevant only while a variable is high enough (e.g. the
# solar output, a tank level): ``gate_variable`` names it, ``gate_min`` is the
# threshold; below it the alert is suppressed with reason ``below_gate``.
# ``require_pv_kw`` is the pre-0030 name of ``gate_min`` — still accepted and
# returned on /v1 (deprecated, removed in /v2). Writing it without a variable
# fills ``gate_variable`` from ALERTD_PV_POWER_VAR, the old global setting.
_VAR_NAME = r"^[a-zA-Z][a-zA-Z0-9_.]*$"
_GATE_VARIABLE = Field(
    default=None, max_length=128, pattern=_VAR_NAME,
    description="Variable the delivery gate reads. With `gate_min`: the alert is "
    "suppressed (`below_gate`) while this variable is below `gate_min`. A missing, "
    "stale or non-numeric value never suppresses (fail-open).",
)
_GATE_MIN = Field(default=None, description="Threshold for `gate_variable` (deliver while value ≥ gate_min).")
# Marked deprecated in the OpenAPI schema only — pydantic's ``deprecated=``
# would also warn on every attribute read inside the service.
_LEGACY_PV = Field(
    default=None, json_schema_extra={"deprecated": True},
    description="Deprecated alias of `gate_min` (pre-0030 name). Removed in /v2.",
)




def _apply_legacy_gate[M: ("TemplateBase", "TemplateUpdate")](model: M) -> M:
    """Map a written ``require_pv_kw`` onto the generic gate fields."""
    if model.require_pv_kw is None or "require_pv_kw" not in model.model_fields_set:
        return model
    if "gate_min" not in model.model_fields_set:
        model.gate_min = model.require_pv_kw
    if "gate_variable" not in model.model_fields_set:
        from ..config import get_settings

        legacy_var = get_settings().pv_power_var
        if legacy_var:
            model.gate_variable = legacy_var
    return model


def _check_quiet_hours(v: Any) -> Any:
    """A template's quiet_hours maps a channel name to a window string like
    ``"22-07"``. Reject a non-string value (e.g. ``{"screen": 123}``) at the
    API boundary instead of letting it raise AttributeError during a fire
    (audit F29)."""
    if v is None:
        return v
    if not isinstance(v, dict):
        raise ValueError("quiet_hours must be a mapping of channel → window string")
    for k, win in v.items():
        if not isinstance(win, str):
            raise ValueError(
                f"quiet_hours[{k!r}] must be a window string like '22-07', "
                f"not {type(win).__name__}"
            )
    return v


class TemplateBase(BaseModel):
    severity: Severity
    icon: str | None = Field(default=None, max_length=8)
    # Free-form grouping for the admin UI. NULL = "Uncategorized".
    # Operator picks from a UI-side predefined list; not enforced
    # server-side so adding a new bucket needs no migration.
    category: str | None = Field(default=None, max_length=32)
    title_template: str = Field(min_length=1)
    message_template: str | None = None
    runbook_url: str | None = Field(default=None, max_length=500)
    description: str | None = None
    locale: str = Field(default="en", max_length=8)
    min_repeat_min: int = Field(default=30, ge=0, le=10080)  # up to 7 days
    gate_variable: str | None = _GATE_VARIABLE
    gate_min: float | None = _GATE_MIN
    require_pv_kw: float | None = _LEGACY_PV
    quiet_hours: dict[str, Any] | None = None
    enabled: bool = True

    @field_validator("quiet_hours")
    @classmethod
    def _validate_quiet_hours(cls, v: Any) -> Any:
        return _check_quiet_hours(v)

    @model_validator(mode="after")
    def _legacy_gate(self) -> TemplateBase:
        return _apply_legacy_gate(self)


class TemplateCreate(TemplateBase):
    type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")

    @field_validator("icon")
    @classmethod
    def _validate_icon(cls, v: str | None) -> str | None:
        return validate_icon(v)

    @field_validator("category")
    @classmethod
    def _normalize_category(cls, v: str | None) -> str | None:
        return normalize_category(v)


class TemplateUpdate(BaseModel):
    severity: Severity | None = None
    icon: str | None = Field(default=None, max_length=8)
    category: str | None = Field(default=None, max_length=32)
    title_template: str | None = None
    message_template: str | None = None
    # Same column caps as create, so a PATCH can't exceed what CREATE
    # enforces and fail at the DB instead of 422 (audit F29).
    runbook_url: str | None = Field(default=None, max_length=500)
    description: str | None = None
    locale: str | None = Field(default=None, max_length=8)
    min_repeat_min: int | None = Field(default=None, ge=0, le=10080)
    gate_variable: str | None = _GATE_VARIABLE
    gate_min: float | None = _GATE_MIN
    require_pv_kw: float | None = _LEGACY_PV
    quiet_hours: dict[str, Any] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _legacy_gate(self) -> TemplateUpdate:
        return _apply_legacy_gate(self)

    @field_validator("icon")
    @classmethod
    def _validate_icon(cls, v: str | None) -> str | None:
        return validate_icon(v)

    @field_validator("category")
    @classmethod
    def _normalize_category(cls, v: str | None) -> str | None:
        return normalize_category(v)

    @field_validator("quiet_hours")
    @classmethod
    def _validate_quiet_hours(cls, v: Any) -> Any:
        return _check_quiet_hours(v)


class TemplateRead(TemplateBase):
    id: int
    type: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _mirror_legacy_gate(self) -> TemplateRead:
        # Old clients still read require_pv_kw; it mirrors gate_min.
        self.require_pv_kw = self.gate_min
        return self

    @field_serializer("created_at", "updated_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so config timestamps aren't read as local (B-13).
        return _as_utc_iso(value)
