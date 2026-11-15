"""Rule DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer, field_validator

from ..core.eval import MISSING_INPUT_PREFIX
from .log import _as_utc_iso


class RuleBase(BaseModel):
    template_type: str = Field(min_length=1, max_length=64)
    condition_expr: str = Field(min_length=1)
    incident_enabled: bool = False
    recovery_expr: str | None = Field(default=None, min_length=1)
    recovery_persist_n: int = Field(default=1, ge=1, le=10000)
    resolved_template_type: str | None = Field(default=None, min_length=1, max_length=64)
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
    incident_enabled: bool | None = None
    recovery_expr: str | None = Field(default=None, min_length=1)
    recovery_persist_n: int | None = Field(default=None, ge=1, le=10000)
    resolved_template_type: str | None = Field(default=None, min_length=1, max_length=64)
    persist_n: int | None = Field(default=None, ge=1, le=10000)
    eval_interval_sec: int | None = Field(default=None, ge=1, le=3600)
    vars_extract: list[str] | None = None
    inhibited_by: list[str] | None = None
    trigger_summary: str | None = None
    trigger_logic_md: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None

    @field_validator("incident_enabled", "recovery_persist_n")
    @classmethod
    def _non_null_lifecycle(cls, value: bool | int | None) -> bool | int:
        if value is None:
            raise ValueError("must not be null")
        return value


EvalStatus = Literal["ok", "no_data", "error"]


def eval_status_of(consecutive_eval_errors: int, last_eval_error: str | None) -> EvalStatus:
    if consecutive_eval_errors > 0:
        return "error"
    if not last_eval_error:
        return "ok"
    return "no_data" if last_eval_error.startswith(MISSING_INPUT_PREFIX) else "error"

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def eval_status(self) -> EvalStatus:
        """``error``: the expression fails (counted towards auto-disable);
        ``no_data``: it is waiting for an input that has no value; ``ok``."""
        return eval_status_of(self.consecutive_eval_errors, self.last_eval_error)

    @field_serializer(
        "last_evaluated_at", "last_fired_at", "created_at", "updated_at"
    )
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so timestamps aren't read as local (B-13).
        return _as_utc_iso(value)


class RuleBulkEnabled(BaseModel):
    """Enable or disable several rules in one transaction (one engine reload)."""

    ids: list[int] = Field(min_length=1, max_length=500)
    enabled: bool


class RuleBulkResult(BaseModel):
    updated: list[int] = Field(default_factory=list)
    unchanged: list[int] = Field(default_factory=list)
    not_found: list[int] = Field(default_factory=list)
