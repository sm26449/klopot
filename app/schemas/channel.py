"""Channel DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .common import ChannelKind
from .log import _as_utc_iso

_QUIET_HOURS_DESC = (
    "This channel's own quiet window, applied by gating in the service "
    'timezone (audit A05). Contract: {"window": "22-07"} (HH or HH:MM, '
    "crosses midnight). Omit/null = never quiet. Separate from a "
    "template's per-channel quiet_hours map."
)


class ChannelBase(BaseModel):
    kind: ChannelKind
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    rate_limit_per_min: int = Field(default=30, ge=0, le=10000)
    quiet_hours: dict[str, Any] | None = Field(default=None, description=_QUIET_HOURS_DESC)


class ChannelCreate(ChannelBase):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")


class ChannelUpdate(BaseModel):
    kind: ChannelKind | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=0, le=10000)
    quiet_hours: dict[str, Any] | None = None


class ChannelRead(ChannelBase):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    # ``config`` is returned MASKED: literal secret fields (bot_token,
    # password, ...) are replaced by ``"<redacted>"``. This map says how
    # each secret field is provided — ``"literal"``, ``"env:<NAME>"``
    # (via the ``*_ref`` sibling) — without exposing the value. Unset
    # fields are omitted. See ``app/secrets_registry.py``.
    secret_fields_set: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so config timestamps aren't read as local (B-13).
        return _as_utc_iso(value)
