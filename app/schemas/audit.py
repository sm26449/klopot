"""Audit log query DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer

from .log import _as_utc_iso


class AuditLogRead(BaseModel):
    """Read shape for an ``audit_log`` row.

    Populated by ``record_change()`` on every CRUD touching a
    resource. ``before`` / ``after`` are JSON snapshots — operators
    use the diff to see exactly what changed.

    ``ts`` is naive UTC at rest (audit #121, v1.3.4); the Pydantic
    serializer emits a Z-suffixed ISO so the UI can convert to the
    operator's local time unambiguously.
    """

    id: int
    ts: datetime
    actor_kind: str
    actor_id: int | None = None
    actor_name: str | None = None
    action: str
    resource_kind: str | None = None
    resource_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    trace_id: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("ts")
    def _serialize_utc_ts(self, value: datetime) -> str | None:
        return _as_utc_iso(value)
