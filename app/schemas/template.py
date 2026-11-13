"""Template DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .common import Severity
from .log import _as_utc_iso


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
    require_pv_kw: float | None = None
    quiet_hours: dict[str, Any] | None = None
    enabled: bool = True

    @field_validator("quiet_hours")
    @classmethod
    def _validate_quiet_hours(cls, v: Any) -> Any:
        return _check_quiet_hours(v)


class TemplateCreate(TemplateBase):
    type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")


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
    require_pv_kw: float | None = None
    quiet_hours: dict[str, Any] | None = None
    enabled: bool | None = None

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

    @field_serializer("created_at", "updated_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so config timestamps aren't read as local (B-13).
        return _as_utc_iso(value)
