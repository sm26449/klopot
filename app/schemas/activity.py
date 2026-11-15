"""Activity log DTOs (docs/ACTIVITY_LOG.md)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .log import _as_utc_iso

BodyMode = Literal["auto", "never", "errors", "always"]


class _Times(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json")
    def _utc(self, value: Any) -> Any:
        return _as_utc_iso(value) if isinstance(value, datetime) else value


class ApiRequestRead(_Times):
    id: int
    ts: datetime
    method: str
    route: str
    path: str
    status: int
    duration_ms: int
    actor_kind: str | None = None
    actor_name: str | None = None
    api_key_id: int | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    trace_id: str | None = None
    rule_id: int | None = None
    expires_at: datetime
    has_request_body: bool = False
    has_response_body: bool = False


class ApiRequestDetail(ApiRequestRead):
    request_body: str | None = None
    response_body: str | None = None


class SourceRow(BaseModel):
    """Requests grouped by who sent them and where."""

    actor_name: str | None
    client_ip: str | None
    method: str
    route: str
    total: int
    by_class: dict[str, int] = Field(description='Counts per status class, e.g. {"2xx": 120, "4xx": 3}.')
    last_seen: str | None


class IgnoredRow(BaseModel):
    """Requests an `ignore` rule kept out of the log — counted only."""

    rule_id: int
    name: str
    pattern: str
    hits: int
    last_hit_at: str | None
    last_ip: str | None


class SourcesResponse(BaseModel):
    hours: int
    sources: list[SourceRow]
    ignored: list[IgnoredRow]


class AttemptRead(_Times):
    id: int
    delivery_id: int | None = None
    notification_id: str | None = None
    channel: str
    kind: str
    attempt_no: int
    started_at: datetime
    duration_ms: int
    outcome: str
    http_status: int | None = None
    retry_after_sec: int | None = None
    provider_ref: str | None = None
    error: str | None = None
    exchange: list[dict[str, Any]] | None = Field(
        default=None, description="HTTP exchanges of the attempt; bodies only for the `admin` scope.")


class SystemEventRead(_Times):
    id: int
    ts: datetime
    source_kind: str
    source_id: int | None = None
    source_name: str
    event: str
    detail: str | None = None


def _norm_method(v: str | None) -> str | None:
    return (v.strip().upper() or None) if v else None


def _norm_status(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().lower()
    if v in ("1xx", "2xx", "3xx", "4xx", "5xx") or (v.isdigit() and 100 <= int(v) <= 599):
        return v
    raise ValueError("match_status must be a class like 4xx or an HTTP status code")


class ActivityRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    position: int = Field(default=100, ge=0, le=100000)
    match_method: str | None = Field(default=None, max_length=8, description="GET, POST… — empty = any.")
    match_path: str = Field(default="*", min_length=1, max_length=191,
                            description="Glob on the request path, e.g. /v1/health* or /v1/inputs/*/webhook.")
    match_status: str | None = Field(default=None, max_length=8, description="2xx, 4xx… or an exact code; empty = any.")
    match_actor: str | None = Field(default=None, max_length=64, description="Glob on the API key / user name.")
    match_ip: str | None = Field(default=None, max_length=64, description="Glob on the client IP, e.g. 10.0.0.*.")
    action: Literal["keep", "ignore"] = "keep"
    keep_days: int | None = Field(default=None, ge=1, le=3650, description="Keep matching rows this long; empty = log_retention_days.")
    request_body: BodyMode = "auto"
    response_body: BodyMode = "auto"

    @field_validator("match_method")
    @classmethod
    def _method(cls, v: str | None) -> str | None:
        return _norm_method(v)

    @field_validator("match_status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        return _norm_status(v)


class ActivityRuleCreate(ActivityRuleBase):
    pass


class ActivityRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None
    position: int | None = Field(default=None, ge=0, le=100000)
    match_method: str | None = None
    match_path: str | None = Field(default=None, min_length=1, max_length=191)
    match_status: str | None = None
    match_actor: str | None = None
    match_ip: str | None = None
    action: Literal["keep", "ignore"] | None = None
    keep_days: int | None = Field(default=None, ge=1, le=3650)
    request_body: BodyMode | None = None
    response_body: BodyMode | None = None

    @field_validator("match_method")
    @classmethod
    def _method(cls, v: str | None) -> str | None:
        return _norm_method(v)

    @field_validator("match_status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        return _norm_status(v)


class ActivityRuleRead(ActivityRuleBase, _Times):
    id: int
    hits: int
    last_hit_at: datetime | None = None
    last_ip: str | None = None


class RulePreview(BaseModel):
    window_hours: int
    checked: int
    matched: int
    examples: list[ApiRequestRead]
