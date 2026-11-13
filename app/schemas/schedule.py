"""Schedule DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .log import _as_utc_iso


def _validate_cron(expr: str) -> str:
    """Reject invalid cron expressions at the schema layer."""
    from croniter import croniter

    try:
        croniter(expr)
    except Exception as e:
        raise ValueError(f"Invalid cron expression: {e}") from e
    return expr


class ScheduleBase(BaseModel):
    cron_expr: str = Field(min_length=1, max_length=64)
    template_type: str = Field(min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("cron_expr")
    @classmethod
    def _check_cron(cls, v: str) -> str:
        return _validate_cron(v)


class ScheduleCreate(ScheduleBase):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")


class ScheduleUpdate(BaseModel):
    cron_expr: str | None = None
    template_type: str | None = None
    context: dict[str, Any] | None = None
    enabled: bool | None = None

    @field_validator("cron_expr")
    @classmethod
    def _check_cron(cls, v: str | None) -> str | None:
        return _validate_cron(v) if v is not None else None


class ScheduleRead(ScheduleBase):
    id: int
    name: str
    last_fired_at: datetime | None = None
    next_fire_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("last_fired_at", "next_fire_at", "created_at", "updated_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so next-fire isn't read as local by the browser (F38).
        return _as_utc_iso(value)
