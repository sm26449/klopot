"""Input DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .common import InputKind
from .log import _as_utc_iso


class InputBase(BaseModel):
    kind: InputKind
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class InputCreate(InputBase):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")


class InputUpdate(BaseModel):
    kind: InputKind | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class InputRead(InputBase):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    # ``config`` is returned MASKED (literal secrets → ``"<redacted>"``);
    # this map says how each secret field is provided (``"literal"`` /
    # ``"env:<NAME>"``). See ``app/secrets_registry.py``.
    secret_fields_set: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so config timestamps aren't read as local (B-13).
        return _as_utc_iso(value)


class InputHealth(BaseModel):
    """Snapshot returned by ``GET /v1/inputs/{id}/health``."""

    name: str
    kind: InputKind
    connected: bool
    last_msg_ts: float | None = None
    msg_count: int = 0
    error: str | None = None
