"""Rule DTOs."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .log import _as_utc_iso


class RuleBase(BaseModel):
    template_type: str = Field(min_length=1, max_length=64)
    condition_expr: str = Field(min_length=1)
    persist_n: int = Field(default=1, ge=1, le=10000)
    eval_interval_sec: int = Field(default=10, ge=1, le=3600)
    vars_extract: list[str] = Field(default_factory=list)
    # Names of rules whose ACTIVE state suppresses this rule's fires
    # (storm correlation). Unknown names are ignored at eval time.
    inhibited_by: list[str] = Field(default_factory=list)
    trigger_summary: str | None = Field(default=None, max_length=500)
    trigger_logic_md: str | None = None
    enabled: bool = True
    sort_order: int = 100


class RuleCreate(RuleBase):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_-]*$")


class RuleUpdate(BaseModel):
    template_type: str | None = None
    condition_expr: str | None = None
    persist_n: int | None = Field(default=None, ge=1, le=10000)
    eval_interval_sec: int | None = Field(default=None, ge=1, le=3600)
    vars_extract: list[str] | None = None
    inhibited_by: list[str] | None = None
    trigger_summary: str | None = None
    trigger_logic_md: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class RuleRead(RuleBase):
    id: int
    name: str
    last_evaluated_at: datetime | None = None
    last_fired_at: datetime | None = None
    fire_count_lifetime: int = 0
    last_eval_error: str | None = None
    consecutive_eval_errors: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "last_evaluated_at", "last_fired_at", "created_at", "updated_at"
    )
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so timestamps aren't read as local (B-13).
        return _as_utc_iso(value)
