"""Pydantic contract for a config import pack (audit A09).

Every section of an imported YAML pack is validated through these DTOs
*before* ``config_io.import_config`` touches the DB. This turns invalid
packs — bad enum values, missing required fields, a scalar where a list
was expected, an unknown ``settings`` key such as ``id`` — into localized
errors (returned as ``plan.errors`` → HTTP 200 ``ok=false``) instead of an
uncaught ``ValueError`` / ``KeyError`` / ``TypeError`` surfacing as a 500.

Design notes:

- ``extra="forbid"`` on every model rejects unknown keys. For ``settings``
  this *is* the whitelist the audit asked for: ``{id: 2}`` is refused
  rather than silently ``setattr``-ing the primary key.
- String ``max_length`` mirrors the DB column widths so an over-long value
  is caught here, not as a truncation/‘Data too long’ error at write time.
- Identifier **name patterns are intentionally NOT enforced**: existing
  production rows must round-trip (export → import) without being rejected
  for a name an older create endpoint allowed. Validation here guarantees
  *applicability* (the row can be written), not naming policy.
- Section lists are checked for **duplicate identifiers** within the same
  pack, which would otherwise collapse into a single confusing upsert.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..schemas.common import ChannelKind, InputKind, Severity, VariableSource
from ..utils.icons import normalize_category, validate_icon

# Settings columns an import may set. Anything else (``id``, ``updated_at``,
# SQLAlchemy internals) is rejected. Kept as a constant so the writer in
# config_io can share the exact whitelist.
SETTINGS_FIELDS = (
    "log_retention_days",
    "audit_retention_days",
    "idempotency_window_sec",
    "default_eval_interval_sec",
    "circuit_breaker_threshold",
    "circuit_breaker_open_sec",
    "bridge_max_queue",
    "timezone",
)

_Strict = ConfigDict(extra="forbid")


class ImportSettings(BaseModel):
    model_config = _Strict

    log_retention_days: int | None = Field(default=None, ge=0)
    audit_retention_days: int | None = Field(default=None, ge=0)
    idempotency_window_sec: int | None = Field(default=None, ge=0)
    default_eval_interval_sec: int | None = Field(default=None, ge=1)
    circuit_breaker_threshold: int | None = Field(default=None, ge=1)
    circuit_breaker_open_sec: int | None = Field(default=None, ge=0)
    bridge_max_queue: int | None = Field(default=None, ge=1)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class ImportInput(BaseModel):
    model_config = _Strict

    name: str = Field(min_length=1, max_length=64)
    kind: InputKind
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ImportTemplate(BaseModel):
    model_config = _Strict

    type: str = Field(min_length=1, max_length=64)
    severity: Severity
    title_template: str = Field(min_length=1)
    icon: str | None = Field(default=None, max_length=8)
    category: str | None = Field(default=None, max_length=32)
    message_template: str | None = None
    runbook_url: str | None = Field(default=None, max_length=500)
    description: str | None = None
    locale: str = Field(default="en", max_length=8)
    min_repeat_min: int = Field(default=30, ge=0, le=10080)
    gate_variable: str | None = Field(default=None, max_length=128, pattern=r"^[a-zA-Z][a-zA-Z0-9_.]*$")
    gate_min: float | None = None
    # Pre-0030 name of gate_min; still imported (with a warning).
    require_pv_kw: float | None = None
    quiet_hours: dict[str, Any] | None = None
    enabled: bool = True

    @field_validator("icon")
    @classmethod
    def _validate_icon(cls, v: str | None) -> str | None:
        return validate_icon(v)

    @field_validator("category")
    @classmethod
    def _normalize_category(cls, v: str | None) -> str | None:
        return normalize_category(v)


class ImportChannel(BaseModel):
    model_config = _Strict

    name: str = Field(min_length=1, max_length=64)
    kind: ChannelKind
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    rate_limit_per_min: int = Field(default=30, ge=0)
    quiet_hours: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _actions_policy(self) -> ImportChannel:
        if self.kind.value == "mqtt":
            from ..channels.mqtt_config import validate_config

            validate_config(self.config)
        if self.kind.value == "telegram":
            from ..channels.telegram_config import validate_actions_config

            validate_actions_config(self.config)
        if self.kind.value == "sms":
            from ..channels.sms_config import upgrade_legacy
            from ..channels.sms_config import validate_config as validate_sms

            # Secrets may be masked placeholders or env refs in an export.
            validate_sms(upgrade_legacy(self.config), require_secrets=False)
        return self


class ImportVariable(BaseModel):
    model_config = _Strict

    name: str = Field(min_length=1, max_length=128)
    source: VariableSource
    input: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    enabled: bool = True


class ImportRule(BaseModel):
    model_config = _Strict

    name: str = Field(min_length=1, max_length=128)
    template_type: str = Field(min_length=1, max_length=64)
    condition_expr: str = Field(min_length=1)
    incident_enabled: bool = False
    recovery_expr: str | None = Field(default=None, min_length=1)
    recovery_persist_n: int = Field(default=1, ge=1, le=10000)
    resolved_template_type: str | None = Field(default=None, min_length=1, max_length=64)
    persist_n: int = Field(default=1, ge=1)
    eval_interval_sec: int = Field(default=10, ge=1)
    vars_extract: list[str] = Field(default_factory=list)
    inhibited_by: list[str] = Field(default_factory=list)
    trigger_summary: str | None = Field(default=None, max_length=500)
    trigger_logic_md: str | None = None
    enabled: bool = True
    sort_order: int = 100


class ImportRoute(BaseModel):
    model_config = _Strict

    template: str = Field(min_length=1, max_length=64)
    channel: str = Field(min_length=1, max_length=64)
    severity_min: Severity = Severity.info
    enabled: bool = True
    channel_overrides: dict[str, Any] | None = None


class ImportSchedule(BaseModel):
    model_config = _Strict

    name: str = Field(min_length=1, max_length=64)
    cron_expr: str = Field(min_length=1, max_length=64)
    template_type: str = Field(min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ImportPack(BaseModel):
    """Top-level import document. Unknown top-level keys are rejected."""

    model_config = _Strict

    version: str | None = None
    settings: ImportSettings | None = None
    inputs: list[ImportInput] | None = None
    templates: list[ImportTemplate] | None = None
    channels: list[ImportChannel] | None = None
    variables: list[ImportVariable] | None = None
    rules: list[ImportRule] | None = None
    routes: list[ImportRoute] | None = None
    schedules: list[ImportSchedule] | None = None

    @model_validator(mode="after")
    def _no_duplicate_identifiers(self) -> ImportPack:
        def dupes(items: list[Any] | None, key: Any) -> list[str]:
            if not items:
                return []
            seen: set[Any] = set()
            out: list[str] = []
            for it in items:
                k = key(it)
                if k in seen:
                    out.append(str(k))
                else:
                    seen.add(k)
            return out

        checks = [
            ("inputs", self.inputs, lambda x: x.name),
            ("templates", self.templates, lambda x: x.type),
            ("channels", self.channels, lambda x: x.name),
            ("variables", self.variables, lambda x: x.name),
            ("rules", self.rules, lambda x: x.name),
            ("schedules", self.schedules, lambda x: x.name),
            ("routes", self.routes, lambda x: (x.template, x.channel)),
        ]
        errors: list[str] = []
        for section, items, key in checks:
            for d in dupes(items, key):
                errors.append(f"{section}: duplicate identifier {d!r} in pack")
        if errors:
            raise ValueError("; ".join(errors))
        return self


def validate_pack(config: dict[str, Any]) -> list[str]:
    """Validate a raw import dict against the pack contract.

    Returns a list of localized, human-readable error strings (empty when
    the pack is structurally valid). Never raises — callers put the result
    straight into ``ImportPlan.errors``.
    """
    from pydantic import ValidationError

    try:
        ImportPack.model_validate(config)
        return []
    except ValidationError as e:
        out: list[str] = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
            out.append(f"{loc}: {err.get('msg', 'invalid')}")
        return out
