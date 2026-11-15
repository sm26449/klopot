"""Read-only operational state; no provider credentials or action capabilities."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer

from .log import _as_utc_iso


class QueueSummary(BaseModel):
    name: str
    states: dict[str, int]
    overdue: int
    oldest_pending_seconds: float
    oldest_overdue_seconds: float


class FailedOperation(BaseModel):
    queue: str
    notification_id: str
    channel: str
    attempts: int
    error: str | None
    created_at: datetime

    @field_serializer("created_at")
    def _utc(self, value: datetime) -> str | None:
        return _as_utc_iso(value)


class OperationsRead(BaseModel):
    queues: list[QueueSummary]
    workers: dict[str, bool]
    telegram: list[dict[str, Any]]
    mqtt: list[dict[str, Any]]
    recent_failures: list[FailedOperation]
