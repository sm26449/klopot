"""Snooze CRUD DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .log import _as_utc_iso

SnoozeScopeLit = Literal["type", "rule", "channel"]


class SnoozeBase(BaseModel):
    scope: SnoozeScopeLit
    target: str = Field(..., min_length=1, max_length=128)
    until: datetime
    # Bounded: the column is TEXT (64 KiB on MySQL), and an over-long reason
    # from an `ack` key answered 500 instead of 422.
    reason: str | None = Field(default=None, max_length=500)


class SnoozeCreate(SnoozeBase):
    """Caller-supplied fields. ``created_by`` is filled server-side
    from the resolved Actor; ``id`` / ``created_at`` are DB-generated."""
    pass


class SnoozeRead(SnoozeBase):
    id: int
    created_by: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("until", "created_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so browsers don't read the instant as local (F38).
        return _as_utc_iso(value)
