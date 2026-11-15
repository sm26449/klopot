"""Web Push DTOs (docs/WEB_PUSH.md)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .log import _as_utc_iso

MinSeverity = Literal["info", "warning", "critical"]
# base64url without padding (what PushSubscription.toJSON() gives).
_B64URL = r"^[A-Za-z0-9_\-]+={0,2}$"


class PushConfig(BaseModel):
    enabled: bool
    public_key: str | None = None
    channel: str | None = None
    reason: str | None = Field(default=None, description="Why push is not available (enabled=false)")


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=16, max_length=255, pattern=_B64URL)
    auth: str = Field(min_length=8, max_length=255, pattern=_B64URL)


class PushSubscriptionCreate(BaseModel):
    """The browser's ``PushSubscription.toJSON()`` plus an optional label."""

    endpoint: str = Field(min_length=12, max_length=1024)
    keys: PushKeys
    label: str | None = Field(default=None, max_length=100)


class PushSubscriptionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    min_severity: MinSeverity | None = None
    enabled: bool | None = None


class PushSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    service: str = Field(description="Push service host and the endpoint's tail — never the full endpoint")
    endpoint_hash: str = Field(description="sha256 of the endpoint: lets a browser find its own device")
    min_severity: MinSeverity
    enabled: bool
    created_by: str | None = None
    created_at: datetime
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    paused_reason: Literal["service", "operator"] | None = Field(
        default=None, description="Who paused the device: the service (after repeated refusals) or an operator")

    @field_serializer("created_at", "last_success_at", "last_failure_at", when_used="json")
    def _utc(self, value: Any) -> Any:
        return _as_utc_iso(value) if isinstance(value, datetime) else value


class PushTestResult(BaseModel):
    ok: bool
    error: str | None = None
    delivered: int = 0
