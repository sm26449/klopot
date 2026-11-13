"""Log query DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


# Audit #121 (2026-05-17, v1.3.3): ``notifications_log`` stores all
# timestamps as naive UTC (the engine and dispatcher call
# ``utc_now()`` before insert — see ``app/core/dispatcher.py:171``,
# ``app/core/engine.py:302``). Pydantic's default serializer emits
# the value without any timezone suffix, which the browser then
# parses as LOCAL — operators saw fire times shifted by the local
# offset (e.g. 09:49 displayed for an event that actually fired at
# 12:49 local).
#
# Stamp a ``Z`` suffix on every datetime field so the browser's
# ``new Date(iso)`` correctly interprets the value as UTC and
# displays it in the operator's local time.
def _as_utc_iso(value: datetime | None) -> str | None:
    """Serialize a naive-UTC datetime as a Z-suffixed ISO string."""
    if value is None:
        return None
    # ``isoformat()`` on a naive datetime emits no suffix; append Z
    # to make the wire format unambiguously UTC.
    s = value.isoformat()
    # Defensive: if upstream code ever sends an aware datetime that
    # serializes to ``+00:00``, normalise to Z. If it's offset to
    # something else, keep the offset (would be a separate bug).
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    if "+" in s[10:] or s.endswith("Z"):
        return s
    return s + "Z"


class LogEntryRead(BaseModel):
    """Read shape for a ``notifications_log`` row."""

    id: str
    template_id: int | None = None
    rule_id: int | None = None
    type: str
    severity: str
    title: str
    message: str | None = None
    vars_payload: dict[str, Any] | None = None
    fired_at: datetime
    dispatched_to: list[str]
    failed_channels: dict[str, str]
    suppressed_reason: str | None = None
    # Settled outcome: sent | partial | failed | suppressed (audit A03).
    # None only for pre-0009 rows the backfill somehow missed.
    delivery_status: str | None = None
    dispatch_latency_ms: int | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    snoozed_until: datetime | None = None
    escalated_at: datetime | None = None
    is_test: bool = False
    source: str | None = None
    trace_id: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("fired_at", "acknowledged_at", "snoozed_until", "escalated_at")
    def _serialize_utc_dates(self, value: datetime | None) -> str | None:
        return _as_utc_iso(value)
