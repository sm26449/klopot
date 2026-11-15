"""Shared schema types — mirrors enums in app.db.models.

These are duplicated rather than imported from the ORM so:
  1. The API layer doesn't pull SQLAlchemy as a transitive dep.
  2. We can rename ORM fields without breaking the API contract.

When adding a new enum value, update both places. CI test in S12
will assert ORM enum members ⊆ API enum members (no DB rows with
unknown values reach clients).
"""
from __future__ import annotations

import enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class Severity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class InputKind(str, enum.Enum):
    mqtt = "mqtt"
    http_poll = "http_poll"
    webhook = "webhook"
    schedule = "schedule"
    sms_inbox = "sms_inbox"
    email_imap = "email_imap"
    alertmanager = "alertmanager"


class VariableSource(str, enum.Enum):
    mqtt = "mqtt"
    aggregate = "aggregate"
    computed = "computed"
    constant = "constant"
    schedule = "schedule"


class ChannelKind(str, enum.Enum):
    mqtt = "mqtt"
    ntfy = "ntfy"
    gotify = "gotify"
    pushover = "pushover"
    ui = "ui"
    banner = "banner"
    telegram = "telegram"
    sms = "sms"
    email = "email"
    push = "push"
    webhook = "webhook"


class SuppressedReason(str, enum.Enum):
    disabled = "disabled"
    snoozed = "snoozed"
    throttled = "throttled"
    persist = "persist"
    gated = "gated"
    duplicate = "duplicate"
    unknown_type = "unknown_type"
    inhibited = "inhibited"  # mirrors db.models (migration 0006)
    below_gate = "below_gate"  # template delivery gate (0010 as pv_power, renamed 0030)


class SnoozeScope(str, enum.Enum):
    type = "type"
    rule = "rule"
    channel = "channel"


# ── Pagination envelope ────────────────────────────────────────────

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard paginated list response.

    Used by every ``GET /v1/<resource>`` endpoint that returns a
    list. Clients can paginate with ``?limit=N&offset=M``.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(from_attributes=True)


# ── Error envelope ─────────────────────────────────────────────────


class ErrorBody(BaseModel):
    """Per-API_DESIGN.md error model. Clients receive this on 4xx/5xx."""

    code: str
    message: str
    details: dict | None = None
    trace_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
