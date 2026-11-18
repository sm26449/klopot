"""SQLAlchemy ORM models — full schema.

Mirrors ``docs/SCHEMA.md``. When adding/changing a column here,
run ``alembic revision --autogenerate -m "..."`` and review the
diff before applying.

All models use:
- ``BIGINT`` for ``id`` columns (16 bytes won't be enough for our
  notifications_log fire-rate over decades, hold the 64-bit line)
- Server-side ``CURRENT_TIMESTAMP`` defaults so DB rows always have
  timestamps even if Python forgets
- ``utf8mb4`` is the connection-level charset (set in compose);
  string columns inherit it
- Explicit indexes annotated with ``index=True`` or via
  ``__table_args__`` for composite cases
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

# The enums live in app.enums (shared with the API schemas); explicit re-exports
# so callers can keep importing them from here.
from ..enums import ActorKind as ActorKind
from ..enums import ChannelKind as ChannelKind
from ..enums import DeliveryState as DeliveryState
from ..enums import DeliveryStatus as DeliveryStatus
from ..enums import InputKind as InputKind
from ..enums import RuleRunState as RuleRunState
from ..enums import Severity as Severity
from ..enums import SnoozeScope as SnoozeScope
from ..enums import SuppressedReason as SuppressedReason
from ..enums import VariableSource as VariableSource
from ..utils.time import utc_now
from .base import Base

# ── Configuration tables ───────────────────────────────────────────


class Input(Base):
    """Declared external value source (MQTT, HTTP poll, webhook, ...)."""

    __tablename__ = "inputs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[InputKind] = mapped_column(Enum(InputKind), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    variables: Mapped[list[Variable]] = relationship(
        back_populates="input_obj",
        cascade="save-update",
        # Let the DB's ON DELETE RESTRICT guard the delete (audit B-01).
        # Without this the ORM disassociates children by emitting
        # UPDATE variables SET input_id=NULL before the parent DELETE, which
        # both widens the binding and hides the constraint from the race.
        passive_deletes=True,
    )


class Variable(Base):
    """Named value extracted from inputs and exposed to rule expressions."""

    __tablename__ = "variables"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    source: Mapped[VariableSource] = mapped_column(Enum(VariableSource), nullable=False)
    input_id: Mapped[int | None] = mapped_column(
        BigInteger,
        # RESTRICT, not SET NULL: a null input_id means "accept any source",
        # so cascading a parent-input delete to NULL would silently widen a
        # bound variable's trust. The delete handler refuses the delete with
        # a 409, but an app-level pre-check races a concurrent variable
        # insert; enforcing RESTRICT at the DB boundary closes that race
        # (audit B-01). Explicit unbinding stays an intentional UPDATE.
        ForeignKey("inputs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    input_obj: Mapped[Input | None] = relationship(back_populates="variables")

    __table_args__ = (
        Index("ix_variables_source", "source"),
        Index("ix_variables_enabled", "enabled"),
    )


class Template(Base):
    """Per-type rendering definition (one template per type)."""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(8))
    # Optional grouping for the admin UI. Free-form string (operator
    # picks from a predefined list in the UI; we don't enforce a
    # whitelist server-side so adding categories doesn't require
    # an alembic migration). NULL = "Uncategorized".
    category: Mapped[str | None] = mapped_column(String(32))
    title_template: Mapped[str] = mapped_column(Text, nullable=False)
    message_template: Mapped[str | None] = mapped_column(Text)
    runbook_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    min_repeat_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # Delivery gate (migration 0030, was require_pv_kw + ALERTD_PV_POWER_VAR):
    # suppressed as ``below_gate`` while gate_variable < gate_min; fail-open.
    gate_variable: Mapped[str | None] = mapped_column(String(128))
    gate_min: Mapped[float | None] = mapped_column(Float)
    quiet_hours: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    channels_link: Mapped[list[TemplateChannel]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_templates_severity", "severity"),
        Index("ix_templates_enabled", "enabled"),
        Index("ix_templates_category", "category"),
    )


class Rule(Base):
    """Trigger logic — one template type can have many rules."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # Soft FK: matches templates.type (no hard FK so a template can be deleted
    # without cascading rule deletions — rule auto-disables instead, visible
    # to operator on next eval).
    template_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Trigger logic
    condition_expr: Mapped[str] = mapped_column(Text, nullable=False)
    incident_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    recovery_expr: Mapped[str | None] = mapped_column(Text)
    recovery_persist_n: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    resolved_template_type: Mapped[str | None] = mapped_column(String(64))
    persist_n: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    eval_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    vars_extract: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Storm correlation (migration 0006): names of rules whose ACTIVE
    # state suppresses this rule's fires (Alertmanager-style
    # inhibition). E.g. every *_stale rule lists the broker-down rule
    # so one root cause pages once instead of 15 times. Soft refs by
    # rule name; unknown/disabled inhibitors are ignored (fail-open).
    inhibited_by: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Documentation FOR USER (visible in UI)
    trigger_summary: Mapped[str | None] = mapped_column(String(500))
    trigger_logic_md: Mapped[str | None] = mapped_column(Text)

    # Lifecycle
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime)
    fire_count_lifetime: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_eval_error: Mapped[str | None] = mapped_column(Text)
    consecutive_eval_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Monotonic generation of the rule's evaluation semantics. Bumped in the
    # SAME transaction that changes the condition expression (audit B-06), so a
    # persisted streak counted against the old expression is stamped with the
    # old epoch and ignored on cold start, and a stale in-flight runtime that
    # writes its old count back cannot resurrect it.
    state_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Where the rule is in its cycle (RuleRunState), since when, and when the
    # condition last became true (rules review RL-32, migration 0045). Written
    # by the engine on a change only; the history is rule_transitions.
    run_state: Mapped[str | None] = mapped_column(String(16))
    run_state_since: Mapped[datetime | None] = mapped_column(DateTime)
    last_true_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Parametric rule (ADR-0005, migration 0046): {"n": ["f1", "f2"]} makes one
    # instance per value, {n} replaced in the condition, recovery,
    # vars_extract and template types. NULL = an ordinary rule. With
    # instances, run_state above is the most urgent of theirs.
    for_each: Mapped[dict[str, list[str]] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    state: Mapped[RuleState | None] = relationship(
        back_populates="rule", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_rules_template_type", "template_type"),
        Index("ix_rules_enabled_sort", "enabled", "sort_order"),
    )


class RuleState(Base):
    """Per-rule runtime counters (separate from config so admin
    edits don't lose ramp-up progress)."""

    __tablename__ = "rule_state"

    rule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("rules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    consecutive_match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovery_match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_match_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_eval_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # The ``Rule.state_epoch`` this counter was written under. On cold start a
    # row whose epoch no longer matches the rule's is discarded as counting
    # against a superseded expression (audit B-06).
    state_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    rule: Mapped[Rule] = relationship(back_populates="state")


class Channel(Base):
    """Output destination declaration."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[ChannelKind] = mapped_column(Enum(ChannelKind), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    quiet_hours: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    templates_link: Mapped[list[TemplateChannel]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_channels_kind", "kind"),
        Index("ix_channels_enabled", "enabled"),
    )


class TemplateChannel(Base):
    """Many-to-many routing between templates and channels with
    optional per-route overrides."""

    __tablename__ = "template_channels"

    template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity_min: Mapped[Severity] = mapped_column(
        Enum(Severity), nullable=False, default=Severity.info
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    channel_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    template: Mapped[Template] = relationship(back_populates="channels_link")
    channel: Mapped[Channel] = relationship(back_populates="templates_link")

    __table_args__ = (PrimaryKeyConstraint("template_id", "channel_id", name="pk_template_channels"),)


# ── Runtime / log tables ───────────────────────────────────────────

# An external episode's identity is case-sensitive (idempotency keys, Grafana
# UIDs): binary collation on MySQL; SQLite already compares bytes.
_EpisodeKey = String(191).with_variant(mysql.VARCHAR(191, collation="utf8mb4_bin"), "mysql")


class Incident(Base):
    """One durable problem episode; acknowledgement and resolution are independent."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("rules.id", ondelete="SET NULL"))
    # A nullable unique FK serialises open episodes per rule. Historical rows
    # clear it on resolution; deleting a rule retains the incident for review.
    active_rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rules.id", ondelete="SET NULL"), unique=True,
    )
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    template_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_template_type: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64))
    opening_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resolution_context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Where the episode comes from (migration 0028): "rule" (the engine),
    # "fire" (POST /v1/fire with an idempotency_key) or "alertmanager".
    # External episodes are identified by source_key; active_source_key is
    # unique while open and cleared on resolution, like active_rule_id.
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="rule", server_default="rule")
    # Compared byte for byte (migration 0036): under the server's
    # utf8mb4_unicode_ci, "DiskFull" and "diskfull" were one episode.
    source_key: Mapped[str | None] = mapped_column(_EpisodeKey)
    active_source_key: Mapped[str | None] = mapped_column(_EpisodeKey, unique=True)
    # The source's own start time (Alertmanager startsAt): a resolution for an
    # older start must not close a newer episode.
    source_started_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def state(self) -> str:
        return "resolved" if self.resolved_at else "active"

    @property
    def duration_sec(self) -> int:
        return max(0, int(((self.resolved_at or utc_now()) - self.opened_at).total_seconds()))

    __table_args__ = (
        Index("ix_incident_resolved_opened", "resolved_at", "opened_at"),
        Index("ix_incident_rule_opened", "rule_id", "opened_at"),
        # The name migration 0028 created (index=True would say "incidents").
        Index("ix_incident_source_key", "source_key"),
    )


class NotificationLog(Base):
    """Canonical history of every fire (dispatched + suppressed)."""

    __tablename__ = "notifications_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("templates.id", ondelete="SET NULL"),
    )
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("rules.id", ondelete="SET NULL"),
    )
    incident_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("incidents.id", ondelete="SET NULL"), index=True,
    )
    incident_event: Mapped[str | None] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    vars_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    fired_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    dispatched_to: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    failed_channels: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    suppressed_reason: Mapped[SuppressedReason | None] = mapped_column(Enum(SuppressedReason))
    # Settled delivery outcome (migration 0009, audit A03). NULL only
    # for rows written by a pre-0009 image; every fire since sets it.
    delivery_status: Mapped[DeliveryStatus | None] = mapped_column(Enum(DeliveryStatus))
    dispatch_latency_ms: Mapped[int | None] = mapped_column(Integer)

    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime)
    # When the escalation was durably queued (legacy rows: attempted).
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime)
    # True for test fires (POST /v1/fire {"test": true}) — excluded
    # from escalation and filterable in the log.
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 191 (utf8mb4 index-safe) so a valid `schedule:<name>` / `test:<name>`
    # origin for a 64-char name can't overflow the column (audit F26).
    source: Mapped[str | None] = mapped_column(String(191))
    trace_id: Mapped[str | None] = mapped_column(String(40))
    # Canonical hash of the fire context — persisted and indexed so
    # idempotency dedup matches by context in SQL instead of scanning the
    # last few rows and missing an in-window duplicate (audit F24).
    context_hash: Mapped[str | None] = mapped_column(String(16))
    # Idempotent marker that this fire's first successful delivery has already
    # been accounted — the template throttle AND the rule lifetime counter —
    # set exactly once via compare-and-set no matter where that first success
    # lands: the synchronous dispatch, or a later retry (audit V08, migration
    # 0019). Kept DISTINCT from dispatched_to / delivery_status so a partial
    # sync success (one channel sent, another pending) followed by a retry can
    # neither be double-counted nor dropped.
    success_counted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    __table_args__ = (
        Index("ix_log_fired", "fired_at"),
        Index("ix_log_type_fired", "type", "fired_at"),
        Index("ix_log_unack", "acknowledged_at", "fired_at"),
        Index("ix_log_severity_fired", "severity", "fired_at"),
        Index("ix_log_suppressed", "suppressed_reason"),
        Index("ix_log_delivery_fired", "delivery_status", "fired_at"),
        Index("ix_log_rule_fired", "rule_id", "fired_at"),
        Index("ix_log_dedup", "type", "is_test", "context_hash", "fired_at"),
    )


class Delivery(Base):
    """Per-channel delivery record — the transactional outbox (A01).

    One row per (notification, channel, purpose). Created in the same transaction
    as the NotificationLog, BEFORE any external send, so a crash can never
    leave a message delivered with no record. A background worker retries
    ``pending`` rows with backoff; semantics are at-least-once.
    """

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notification_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notifications_log.id", ondelete="CASCADE"), nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(16), nullable=False, default="notification", server_default="notification",
    )
    state: Mapped[DeliveryState] = mapped_column(
        Enum(DeliveryState), nullable=False, default=DeliveryState.pending,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Transport identity + channel, distinct for escalation and stable across
    # retries so a destination supporting dedup can drop duplicates.
    idempotency_key: Mapped[str] = mapped_column(String(130), nullable=False)
    # The per-route channel overrides captured at enqueue time (audit F03),
    # kept for audit/visibility of what the route contributed.
    channel_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # The FULL effective send config (channel base config merged with the
    # route override) frozen at enqueue time, so every retry targets the
    # SAME destination/credentials as the first attempt even if the channel
    # is edited meanwhile (audit V01). NULL for rows enqueued before this
    # column existed — the worker falls back to the legacy live merge.
    effective_config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # The channel's adapter KIND frozen at enqueue time (audit B-02). The adapter
    # is chosen from this, not the live channel row, so repurposing a channel
    # (e.g. webhook → ui) can't make the worker feed a frozen webhook config to a
    # different adapter and falsely mark the delivery sent. NULL for rows
    # enqueued before this column — the worker falls back to the live kind.
    effective_kind: Mapped[str | None] = mapped_column(String(32))
    # Callback capabilities are prepared with the outbox, before any send.
    # Never exposed by the delivery API or configuration export.
    action_keyboard: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Provider's id for the sent message when the channel reports one
    # (e.g. the ntfy message id); migration 0028.
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    last_error: Mapped[str | None] = mapped_column(String(500))
    # Claim/lease: while set in the future this row is owned by the attempt
    # that leased it (the dispatcher's sync attempt, or a worker retry), so
    # another worker cannot double-send it (audit F04). Cleared when the
    # attempt settles the row.
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    action_tokens: Mapped[list[ChannelActionToken]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "notification_id", "channel", "purpose", name="uq_delivery_notif_channel_purpose",
        ),
        Index("ix_delivery_due", "state", "next_attempt_at"),
        # Every send looks its delivery rows up by this key (channels/manager.py).
        Index("ix_delivery_idempotency_key", "idempotency_key"),
        # The Pushover receipt poll looks for "pushover:receipt:%" every minute;
        # a prefix range on this index reads receipt rows only (review K13).
        Index("ix_delivery_provider_ref", "provider_ref"),
    )


class TelegramBotState(Base):
    """One persisted polling cursor per bot credential identity; no token stored."""

    __tablename__ = "telegram_bot_state"
    bot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    next_offset: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime)


class ChannelActionToken(Base):
    __tablename__ = "channel_action_tokens"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    delivery_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    bot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_user_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    any_chat_member: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivery: Mapped[Delivery] = relationship(back_populates="action_tokens")


class ChannelProviderMessage(Base):
    """Provider receipts, including successful retries and ambiguous-send callbacks."""

    __tablename__ = "channel_provider_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    bot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    view_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (
        UniqueConstraint("provider", "bot_key", "chat_id", "message_id", name="uq_provider_message"),
    )


class LifecycleCommand(Base):
    """An action owed to a provider about one delivery (migration 0029), e.g.
    cancelling a Pushover emergency receipt once the alert is acknowledged.
    Retried by app/core/provider_lifecycle.py; one per (delivery, action)."""

    __tablename__ = "lifecycle_commands"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    __table_args__ = (
        UniqueConstraint("delivery_id", "action", name="uq_lifecycle_command"),
        Index("ix_lifecycle_command_due", "state", "next_attempt_at"),
    )


class InboundEvent(Base):
    """A provider event applied once (migration 0029): the unique
    (provider, event_key) makes a repeated callback or poll a no-op."""

    __tablename__ = "inbound_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_key: Mapped[str] = mapped_column(String(191), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    result: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("provider", "event_key", name="uq_inbound_event"),
        Index("ix_inbound_events_received", "received_at"),   # retention (0039)
    )


class ChannelActionCommand(Base):
    """Accepted local actions, applied once transactionally with their audit."""

    __tablename__ = "channel_action_commands"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    delivery_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, unique=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (Index("ix_action_command_due", "state", "next_attempt_at"),)


class ChannelEvent(Base):
    """Minimal provider inbox; message bodies and callback secrets are omitted."""

    __tablename__ = "channel_events"
    bot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    command_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("channel_action_commands.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, index=True)


class ChannelProviderCommand(Base):
    """Durable, independently retried provider-side feedback."""

    __tablename__ = "channel_provider_commands"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reference_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("channel_provider_messages.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False, default="clear_actions")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (
        UniqueConstraint("reference_id", "operation", name="uq_provider_command"),
        Index("ix_provider_command_due", "state", "next_attempt_at"),
    )


class DedupClaim(Base):
    """Atomic admission claim for a fire context (audit R01).

    One row per ``(type, is_test, context_hash)``. A fire claims its slot
    with an atomic upsert that only overwrites a *stale* claim; the winner
    of a concurrent race is whichever claim holds the row, so two
    simultaneous identical fires can't both create a notification. Stale
    rows are reclaimed on the next fire and pruned by retention.
    """

    __tablename__ = "dedup_claims"

    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_test: Mapped[bool] = mapped_column(Boolean, primary_key=True)
    context_hash: Mapped[str] = mapped_column(String(16), primary_key=True)
    notification_id: Mapped[str] = mapped_column(String(64), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_dedup_claimed_at", "claimed_at"),
    )


class ThrottleState(Base):
    """Last-fire tracker per template type and pool: real fires and test fires
    are throttled apart (migration 0040), so a test never delays a real alert
    — the same split as ``dedup_claims``."""

    __tablename__ = "throttle_state"

    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_test: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=False, server_default=false())
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime)
    persist_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    persist_last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    # In-flight per-type cooldown reservation (audit B-10). Taken atomically at
    # admission so two distinct-context fires can't both pass the success-
    # anchored throttle before either has succeeded; released on terminal
    # failure, and superseded by last_fired_at once a fire succeeds.
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime)
    reserved_by: Mapped[str | None] = mapped_column(String(64))


class Snooze(Base):
    """Temporary mute. scope = type / rule / channel."""

    __tablename__ = "snooze"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[SnoozeScope] = mapped_column(Enum(SnoozeScope), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("ix_snooze_scope_target", "scope", "target"),
        Index("ix_snooze_until", "until"),
    )


class Schedule(Base):
    """Cron-driven fires."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False)
    template_type: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (Index("ix_schedules_next_enabled", "next_fire_at", "enabled"),)


class ScheduleOccurrence(Base):
    """Fired-occurrence guard for cron schedules (audit V05).

    One row per ``(schedule_id, scheduled_at)``. The schedule service inserts
    it in the SAME transaction that advances ``next_fire_at`` and persists the
    notification intent, so a given occurrence fires at most once even under a
    double-tick or a second instance — the composite primary key rejects the
    duplicate. ``notification_id`` links the occurrence to the fire it produced
    (best-effort). Pruned by retention once its occurrence time ages out.
    """

    __tablename__ = "schedule_occurrences"

    schedule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("schedules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    notification_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (Index("ix_schedule_occ_scheduled_at", "scheduled_at"),)


# ── Auth & audit ───────────────────────────────────────────────────


class ApiKey(Base):
    """Service-to-service auth credential."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    # sha256 hex of a generated key (auth.key_digest): the lookup that needs no
    # bcrypt. NULL for keys issued before 0034 until their first use, and for
    # operator-chosen keys always.
    key_digest: Mapped[str | None] = mapped_column(String(64))
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=lambda: ["fire"])
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_used_ip: Mapped[str | None] = mapped_column(String(45))
    # The addresses (IPs or CIDRs, normalised) the key may be used from;
    # NULL or empty = any address. Checked on every request (auth.py), after
    # the key itself, against the real client address (utils/client_ip.py).
    allowed_cidrs: Mapped[list[str] | None] = mapped_column(JSON)
    # Requests a minute the key may make (GCRA, utils/rate_limit.py); NULL =
    # no limit. Over it: 429 with Retry-After (auth.py).
    rate_limit_per_min: Mapped[int | None] = mapped_column(Integer)
    # Template types (or fnmatch patterns) the key may fire through /v1/fire;
    # NULL or empty = every type. Checked per request (api/v1/fire.py).
    allowed_types: Mapped[list[str] | None] = mapped_column(JSON)
    rotated_from_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("ix_api_keys_prefix", "key_prefix"),
        Index("uq_api_keys_key_digest", "key_digest", unique=True),
        Index("ix_api_keys_enabled", "enabled"),
    )


class AuditLog(Base):
    """Admin action history (separate from notifications_log)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    actor_kind: Mapped[ActorKind] = mapped_column(Enum(ActorKind), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    actor_name: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_kind: Mapped[str | None] = mapped_column(String(32))
    # 191 (utf8mb4 index-safe) so a 128-char variable name — a valid
    # external identifier — fits without overflowing the commit (audit F25).
    resource_id: Mapped[str | None] = mapped_column(String(191))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    trace_id: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index("ix_audit_ts", "ts"),
        Index("ix_audit_actor_ts", "actor_id", "ts"),
        Index("ix_audit_action_ts", "action", "ts"),
        Index("ix_audit_resource", "resource_kind", "resource_id"),
    )


# ── Activity log (migration 0032, docs/ACTIVITY_LOG.md) ─────────────
# Written off the hot path by app.core.activity (a batching writer), swept by
# retention with log_retention_days. Outcome / event values are plain strings
# (no ENUM) so adding one never needs a migration.

# Long request bodies (webhook payloads up to 64 KB): TEXT on SQLite, MEDIUMTEXT on MySQL.
_LongText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


class DeliveryAttempt(Base):
    """One attempt to hand a message to a provider (alert, escalation, test)."""

    __tablename__ = "delivery_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    delivery_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("deliveries.id", ondelete="CASCADE"))
    notification_id: Mapped[str | None] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)          # alert | escalation | test
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)       # sent | failed | deferred | permanent | timeout
    http_status: Mapped[int | None] = mapped_column(Integer)
    retry_after_sec: Mapped[int | None] = mapped_column(Integer)
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(String(500))
    exchange: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_attempts_delivery", "delivery_id"),
        Index("ix_attempts_notification", "notification_id"),
        Index("ix_attempts_channel_ts", "channel", "started_at"),
        Index("ix_attempts_ts", "started_at"),
    )


class ApiRequest(Base):
    """One HTTP request Klopot received (policy: docs/ACTIVITY_LOG.md)."""

    __tablename__ = "api_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    route: Mapped[str] = mapped_column(String(191), nullable=False)        # template: /v1/inputs/{input_id}/webhook
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actor_kind: Mapped[str | None] = mapped_column(String(16))             # api_key | user
    actor_name: Mapped[str | None] = mapped_column(String(64))
    api_key_id: Mapped[int | None] = mapped_column(BigInteger)
    client_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    trace_id: Mapped[str | None] = mapped_column(String(40))
    request_body: Mapped[str | None] = mapped_column(_LongText)
    response_body: Mapped[str | None] = mapped_column(Text)
    # When retention deletes the row: ts + the matching rule's keep_days, else
    # ts + log_retention_days. Lets a rule keep health probes for one day only.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    rule_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        Index("ix_api_requests_ts", "ts"),
        Index("ix_api_requests_expires", "expires_at"),
        Index("ix_api_requests_route_ts", "route", "ts"),
        Index("ix_api_requests_status_ts", "status", "ts"),
        Index("ix_api_requests_trace", "trace_id"),
    )


class ActivityRule(Base):
    """What the request log keeps for requests matching a pattern (first match wins).

    action: ``keep`` (retention = keep_days or log_retention_days) or ``ignore``
    (not stored — only counted in hits / last_hit_at / last_ip, so the
    operator still sees that such requests arrive).
    request_body / response_body: ``auto`` (the built-in policy), ``never``,
    ``errors`` (status >= 400), ``always``.
    """

    __tablename__ = "activity_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    match_method: Mapped[str | None] = mapped_column(String(8))            # NULL = any
    match_path: Mapped[str] = mapped_column(String(191), nullable=False, default="*")  # glob on the path
    match_status: Mapped[str | None] = mapped_column(String(8))            # NULL | 2xx | 3xx | 4xx | 5xx | 401 …
    match_actor: Mapped[str | None] = mapped_column(String(64))            # glob on key / user name
    match_ip: Mapped[str | None] = mapped_column(String(64))               # glob on the client IP
    action: Mapped[str] = mapped_column(String(8), nullable=False, default="keep")   # keep | ignore
    keep_days: Mapped[int | None] = mapped_column(Integer)
    request_body: Mapped[str] = mapped_column(String(8), nullable=False, default="auto")
    response_body: Mapped[str] = mapped_column(String(8), nullable=False, default="auto")
    hits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (Index("ix_activity_rules_position", "position"),)


class RuleInstance(Base):
    """The runtime state of one instance of a parametric rule (ADR-0005,
    migration 0046): what ``rule_state`` and the rule's own run-state columns
    hold for an ordinary rule."""

    __tablename__ = "rule_instances"

    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rules.id", ondelete="CASCADE"), primary_key=True,
    )
    instance: Mapped[str] = mapped_column(String(32), primary_key=True)
    consecutive_match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovery_match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_state: Mapped[str | None] = mapped_column(String(16))
    run_state_since: Mapped[datetime | None] = mapped_column(DateTime)
    last_true_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_eval_error: Mapped[str | None] = mapped_column(Text)


class RuleTransition(Base):
    """A change of a rule's run state (rules review RL-32): one row per
    change, never per tick; pruned with the log (ALERTD_LOG_RETENTION_DAYS)."""

    __tablename__ = "rule_transitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rules.id", ondelete="CASCADE"), nullable=False,
    )
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(16))
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(255))
    # The instance of a parametric rule ("" for an ordinary rule; 0046).
    instance: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")

    __table_args__ = (
        Index("ix_rule_transitions_rule", "rule_id", "id"),
        Index("ix_rule_transitions_at", "at"),
    )


class SystemEvent(Base):
    """A state change of an input, rule or channel (never per tick / message)."""

    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)   # input | rule | channel
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index("ix_system_events_ts", "ts"),
        Index("ix_system_events_source", "source_kind", "source_id", "ts"),
    )


# ── Human auth (migration 0008, admin UI) ──────────────────────────


class AdminUser(Base):
    """Browser-login account for the admin UI.

    v1 provisions exactly one row (``admin``) via the bootstrap seed;
    the table shape already allows more users / roles so a later
    multi-user phase needs no schema change. Passwords are argon2id
    PHC strings (``app/core/passwords.py``)."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Set by the bootstrap seed and by the break-glass CLI reset; the
    # API refuses cookie-authenticated writes (other than the password
    # change itself) while it is true.
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    sessions: Mapped[list[AdminSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AdminSession(Base):
    """Opaque browser session (docs/AUTH_MODEL.md, decision D3).

    The cookie carries a 256-bit random token; only its sha256 is
    stored, so a DB dump cannot be replayed. ``csrf_token`` is the
    double-submit value the SPA echoes in ``X-CSRF-Token``. All
    timestamps naive UTC."""

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # min(created_at + SESSION_MAX_DAYS, last_seen_at + SESSION_IDLE_HOURS)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[AdminUser] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_user_active", "user_id", "revoked_at", "expires_at"),
        Index("ix_sessions_last_seen", "last_seen_at"),    # retention (0039)
    )


class LoginAttempt(Base):
    """Login outcome per attempt — the sliding-window lockout source
    (``app/core/login_guard.py``). Pruned by the retention service."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        Index("ix_attempts_user_ts", "username", "ts"),
        Index("ix_attempts_ip_ts", "ip", "ts"),
        Index("ix_login_attempts_ts", "ts"),               # retention (0039)
    )


# ── Settings (single-row) ──────────────────────────────────────────


class Settings(Base):
    """Global config — single row enforced by check constraint."""

    __tablename__ = "settings"

    # Note: autoincrement=False so MySQL accepts the singleton CHECK constraint
    # (CHECK can't reference an auto-increment column).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    log_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    audit_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    idempotency_window_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    default_eval_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    circuit_breaker_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    circuit_breaker_open_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    bridge_max_queue: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (CheckConstraint("id = 1", name="settings_singleton"),)


class PushSubscription(Base):
    """One browser / installed app that receives Web Push (docs/WEB_PUSH.md).

    ``endpoint`` is the push-service URL the browser handed us (Apple,
    Google, Mozilla, Microsoft — allowlisted); ``p256dh`` / ``auth`` are the
    device's public encryption keys (not secrets: they only encrypt *to* the
    device). Unique by ``endpoint_hash`` = sha256(endpoint).
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint_hash", name="uq_push_subscriptions_endpoint_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String(1024), nullable=False)
    endpoint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    min_severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False, default=Severity.warning)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Who paused it (migration 0037): "service" (20 refusals in a row) or
    # "operator"; NULL while enabled. Recorded, never inferred (review K11).
    paused_reason: Mapped[str | None] = mapped_column(String(16))


# ── Future / multi-user ────────────────────────────────────────────


class UserPref(Base):
    """Per-user preferences. Reserved; silent in v1."""

    __tablename__ = "user_prefs"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
