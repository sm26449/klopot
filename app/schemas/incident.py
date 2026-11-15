"""Incident API: human acknowledgement never implies recovery."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .log import _as_utc_iso


class IncidentRead(BaseModel):
    id: str
    rule_id: int | None
    rule_name: str
    template_type: str
    resolved_template_type: str | None
    severity: str
    title: str
    state: Literal["active", "resolved"]
    opened_at: datetime
    resolved_at: datetime | None
    resolution_reason: str | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    duration_sec: int
    # rule (engine) | fire (POST /v1/fire idempotency_key) | alertmanager
    source_kind: str = "rule"
    source_key: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("opened_at", "resolved_at", "acknowledged_at")
    def _utc(self, value: datetime | None) -> str | None:
        return _as_utc_iso(value)


class IncidentDetail(IncidentRead):
    opening_context: dict[str, Any]
    resolution_context: dict[str, Any] | None


class ResolveIncidentRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=450, pattern=r"\S")
