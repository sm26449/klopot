"""The enums shared by the database models and the API schemas.

One definition each: the values are at once what MySQL stores and what the
API sends, so the two could never differ — they used to be written twice
(``app.db.models`` and ``app.schemas.common``) and kept in step by hand. This
module imports neither SQLAlchemy nor pydantic, so the API layer still does
not pull in the ORM.

``StrEnum``: ``str(Severity.critical)`` and ``f"{…}"`` give ``"critical"``,
the value — a plain ``(str, Enum)`` gave ``"Severity.critical"``. Comparisons
with strings, JSON and the database (names equal values) are unchanged.
"""
from __future__ import annotations

import enum


class Severity(enum.StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class InputKind(enum.StrEnum):
    mqtt = "mqtt"
    http_poll = "http_poll"
    webhook = "webhook"
    schedule = "schedule"
    sms_inbox = "sms_inbox"
    email_imap = "email_imap"
    alertmanager = "alertmanager"


class VariableSource(enum.StrEnum):
    mqtt = "mqtt"
    aggregate = "aggregate"
    computed = "computed"
    constant = "constant"
    schedule = "schedule"


class ChannelKind(enum.StrEnum):
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


class SuppressedReason(enum.StrEnum):
    disabled = "disabled"
    snoozed = "snoozed"
    throttled = "throttled"
    persist = "persist"
    gated = "gated"
    duplicate = "duplicate"
    unknown_type = "unknown_type"
    inhibited = "inhibited"  # a declared inhibitor rule is active (0006)
    below_gate = "below_gate"  # template gate: gate_variable below gate_min (0010 as pv_power, renamed 0030)


class DeliveryStatus(enum.StrEnum):
    """Settled outcome of a fire (migration 0009, audit A03).

    Persisted alongside ``suppressed_reason`` so the log, dashboard,
    stats, and dedup replay report the TRUTH instead of inferring
    "delivered" from the mere absence of a suppression reason (a row
    with ``suppressed_reason IS NULL`` but every channel failed is a
    FAILED delivery, not a success).
    """

    sent = "sent"              # ≥1 channel succeeded, none failed
    partial = "partial"        # ≥1 channel succeeded AND ≥1 failed
    failed = "failed"          # dispatch attempted, zero channels succeeded
    suppressed = "suppressed"  # gated before dispatch (see suppressed_reason)
    pending = "pending"        # ≥1 delivery still queued/retrying (0011, A01)
    cancelled = "cancelled"    # recovered incident, no delivery still needed


class DeliveryState(enum.StrEnum):
    """Per-channel delivery state in the transactional outbox (A01)."""

    pending = "pending"   # queued or awaiting the next retry
    sent = "sent"         # delivered to this channel
    failed = "failed"     # permanently failed (max attempts or non-retryable)
    cancelled = "cancelled"  # acknowledged escalation or recovered incident


class SnoozeScope(enum.StrEnum):
    type = "type"
    rule = "rule"
    channel = "channel"


class ActorKind(enum.StrEnum):
    api_key = "api_key"
    jwt = "jwt"
    system = "system"
    user = "user"  # browser session of an admin_users row (migration 0008)
