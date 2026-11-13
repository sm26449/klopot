"""Variable DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .common import VariableSource
from .log import _as_utc_iso


class VariableBase(BaseModel):
    source: VariableSource
    input_id: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    enabled: bool = True


class VariableCreate(VariableBase):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z][a-zA-Z0-9_.]*$")


class VariableUpdate(BaseModel):
    source: VariableSource | None = None
    input_id: int | None = None
    config: dict[str, Any] | None = None
    description: str | None = None
    enabled: bool | None = None


class VariableRead(VariableBase):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime

    # Runtime state — populated from the in-memory state cache at
    # serialization time (not stored on the row). NULL when the
    # variable has never received a value.
    last_value: Any | None = None
    last_value_at: datetime | None = None
    age_sec: float | None = None
    is_stale: bool | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at", "last_value_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so last_value_at isn't read as local time (F38).
        return _as_utc_iso(value)


# ── State endpoint shape ────────────────────────────────────────


class VarState(BaseModel):
    """One entry in ``GET /v1/state``."""

    name: str
    value: Any
    age_sec: float
    wall_ts: float
    source_topic: str | None = None
    source_kind: str = "unknown"


class StateResponse(BaseModel):
    """``GET /v1/state`` body."""

    variables: list[VarState]
    cache_size: int
    last_mqtt_ts: float | None = None
