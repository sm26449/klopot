"""Notification dispatcher — orchestrates fire() end-to-end.

Flow:

  1. Load template by type
  2. Disposition: inhibition (engine-set) or the gating pipeline
     (enabled / snoozed / throttled / quiet) → either a
     suppressed_reason or the routed channel set. Computed BEFORE
     dedup so idempotency is disposition-aware (audit A02).
  3. Idempotency check (same type + is_test + vars hash, 5 min) →
     coalesce onto a same-disposition recent row (see
     ``delivery_status.should_coalesce``); replay its REAL settled
     status (audit A03), no new fire.
  4. Render title + message
  5. Persist to notifications_log with ``delivery_status``:
     - if suppressed → suppressed_reason + status=suppressed
     - else → dispatch via ChannelManager, status derived from the
       per-channel outcome (sent / partial / failed)
  6. Return DispatchResult

Returns a typed DispatchResult so callers (engine, /v1/fire,
/v1/rules/{id}/test) get the same shape.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time as _time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    Channel,
    DeliveryStatus,
    NotificationLog,
    Severity,
    SuppressedReason,
    Template,
    TemplateChannel,
)
from ..utils.time import utc_now
from . import gating, rendering
from .dedup_claims import claim_fire, release_claim
from .delivery_status import should_coalesce, status_of

logger = logging.getLogger(__name__)

# ``notifications_log.title`` is String(255); the rendered title is
# truncated to fit so a long template/context never 500s on insert
# (audit A04). ``message`` is TEXT, so it needs no cap.
_TITLE_MAX = 255


# ── Public types ──────────────────────────────────────────────────


@dataclass
class FireEnvelope:
    """The shape callers post to ``/v1/fire`` and the engine builds
    when a rule matches."""

    type: str
    context: dict[str, Any]
    test: bool = False
    source: str | None = None
    rule_id: int | None = None
    idempotency_key: str | None = None  # optional caller-supplied
    # Set by the ENGINE when a declared inhibitor rule is currently
    # active (storm correlation): the fire is logged with
    # suppressed_reason=inhibited instead of dispatching.
    inhibited_by_active: str | None = None


@dataclass
class DispatchResult:
    """Returned by ``fire()`` to callers."""

    id: str
    dispatched: bool
    channels: list[str]
    suppressed_reason: str | None
    title: str
    message: str
    severity: str
    # Settled outcome: sent | partial | failed | suppressed (audit A03).
    # ``dispatched`` stays for back-compat but is now derived from this
    # (True only for sent/partial) so a fully-failed fire never reports
    # dispatched=True.
    status: str = "sent"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dispatched": self.dispatched,
            "channels": self.channels,
            "suppressed_reason": self.suppressed_reason,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
        }


# ── Public entry point ────────────────────────────────────────────


def _persist_suppressed(
    session: AsyncSession,
    envelope: FireEnvelope,
    template: Template,
    notif_id: str,
    trace_id: str | None,
    title: str,
    message: str,
    reason: str,
) -> DispatchResult:
    """Persist a suppressed NotificationLog (no dispatch) and build its result.

    Shared by the gating-disposition suppression (inhibited/gated/quiet/
    throttled) and the atomic per-type cooldown loser (audit B-10), so both
    emit the same visible suppressed row and metric.
    """
    row = NotificationLog(
        id=notif_id,
        trace_id=trace_id,
        template_id=template.id,
        rule_id=envelope.rule_id,
        type=template.type,
        severity=template.severity,
        title=title,
        message=message,
        vars_payload=_json_safe(envelope.context),
        context_hash=_vars_hash(_json_safe(envelope.context)),
        dispatched_to=[],
        failed_channels={},
        suppressed_reason=SuppressedReason(reason),
        delivery_status=DeliveryStatus.suppressed,
        source=envelope.source,
        is_test=envelope.test,
        # Explicit UTC — the column's server default is MySQL local
        # time, which silently skewed the idempotency window by the
        # UTC offset (migration 0005).
        fired_at=utc_now(),
    )
    session.add(row)
    from ..metrics import FIRES_TOTAL
    FIRES_TOTAL.labels(
        type=template.type,
        severity=template.severity.value,
        suppressed=reason,
    ).inc()
    return DispatchResult(
        id=notif_id,
        dispatched=False,
        channels=[],
        suppressed_reason=reason,
        status=DeliveryStatus.suppressed.value,
        title=title, message=message,
        severity=template.severity.value,
    )


async def fire(envelope: FireEnvelope, session: AsyncSession) -> DispatchResult:
    """Dispatch a notification.

    The caller commits the session — we don't commit here so the
    dispatcher is composable inside larger transactions (e.g., the
    engine batches multiple fires per tick).
    """
    template = await _load_template(session, envelope.type)
    if template is None:
        return await _result_for_unknown_type(envelope, session)

    # 1. Disposition — decide suppressed-vs-dispatch BEFORE dedup so the
    # idempotency check is disposition-aware (audit A02). An inhibitor
    # (engine-set) or a gate denial yields a suppressed_reason; otherwise
    # we hold the routed channels for dispatch.
    overrides_by_name: dict[str, dict[str, Any] | None] = {}
    if envelope.inhibited_by_active:
        suppressed_reason = "inhibited"
        channels: list[str] = []
    else:
        routes = await _resolve_routes(session, template)
        channel_names = [name for name, _ in routes]
        overrides_by_name = {name: ov for name, ov in routes if ov}
        decision = await gating.evaluate(
            gating.GateInput(
                template=template,
                rule_id=envelope.rule_id,
                channel_names=channel_names,
                test=envelope.test,
            ),
            session,
        )
        if decision.allowed:
            suppressed_reason = None
            channels = decision.channels
        else:
            suppressed_reason = decision.reason or "gated"
            channels = []

    # 2. Idempotency — coalesce only a same-disposition recent fire
    # (see delivery_status.should_coalesce + the is_test-aware query).
    existing = await _find_recent_dup(session, envelope, template, suppressed_reason)
    if existing is not None:
        return existing

    # 3. Render (title bounded to the column width — audit A04)
    title = rendering.render(template.title_template, envelope.context)[:_TITLE_MAX]
    message = rendering.render(template.message_template, envelope.context)
    if envelope.inhibited_by_active:
        message += f" [inhibited by {envelope.inhibited_by_active}]"

    notif_id = _generate_id()
    trace_id = _current_trace()

    # 4a. Suppressed — persist with suppressed_reason, dispatch nothing.
    if suppressed_reason is not None:
        return _persist_suppressed(
            session, envelope, template, notif_id, trace_id,
            title, message, suppressed_reason,
        )

    # 4b. Transactional outbox (audit A01): persist the NotificationLog +
    # a Delivery row per channel BEFORE any external send, commit that
    # durable intent, then make a synchronous first attempt. Channels that
    # fail with a retryable error stay pending for the DeliveryWorker.
    from ..channels import Notification
    from ..channels.manager import DispatchOutcome, get_channel_manager

    # 4b-0. Atomic admission (audit R01): claim this (type, context) slot so
    # two simultaneous identical fires can't both pass the SELECT-based dedup
    # and each create a notification. _find_recent_dup already coalesced onto
    # any older settled row; this closes the narrow concurrent window before
    # the winner commits its log. Test fires are exempt (duplicate test rows
    # send nothing and are used intentionally for repeated probes).
    from ..config import get_settings as _get_settings
    from . import outbox
    ctx_hash = _vars_hash(_json_safe(envelope.context))
    claimed = False
    _win = max(0, _get_settings().idempotency_window_sec)
    if _win > 0 and not envelope.test:
        _cnow = utc_now()
        _winner = await claim_fire(
            session, template.type, ctx_hash,
            notif_id, _cnow, _cnow - timedelta(seconds=_win),
        )
        claimed = _winner == notif_id
        if _winner != notif_id:
            # A concurrent fire won the slot — coalesce onto it instead of
            # creating a duplicate notification, replaying its REAL current
            # status rather than assuming pending (audit V04). The winner may
            # not have committed its log yet (a true concurrent race) → pending.
            win_log = await session.get(NotificationLog, _winner)
            win_status = (
                status_of(win_log) if win_log is not None else DeliveryStatus.pending
            )
            return DispatchResult(
                id=_winner,
                dispatched=win_status in (DeliveryStatus.sent, DeliveryStatus.partial),
                channels=list(win_log.dispatched_to or []) if win_log is not None else [],
                suppressed_reason=(
                    win_log.suppressed_reason.value
                    if win_log is not None and win_log.suppressed_reason else None
                ),
                status=win_status.value,
                title=title, message=message, severity=template.severity.value,
            )

    # 4b-0b. Per-type cooldown admission (audit B-10). The gating throttle
    # (gating._is_throttled) is anchored on the last *successful* fire, so two
    # distinct-context fires racing before the first success both pass it and
    # both send despite min_repeat_min. Reserve the type atomically in this
    # durable-intent transaction (admission-anchored) so only one distinct fire
    # per window is admitted; the losers are suppressed as throttled. Identical
    # fires are already coalesced by the context claim above, so only a
    # distinct-context racer reaches and loses this reservation. The reservation
    # is released on terminal failure (below + the worker) and superseded by the
    # confirmed cooldown (record_fire) on first success.
    if template.min_repeat_min > 0 and not envelope.test:
        _rnow = utc_now()
        _holder = await gating.reserve_type_slot(
            session, template.type, notif_id, _rnow,
            _rnow - timedelta(seconds=template.min_repeat_min * 60),
        )
        if _holder != notif_id:
            # Lost the cooldown slot to a concurrent/recent fire. Release the
            # context claim we just won so this suppressed row holds no admission
            # claim, matching the gating-path throttle suppressions.
            if claimed:
                await release_claim(session, template.type, ctx_hash, notif_id)
            return _persist_suppressed(
                session, envelope, template, notif_id, trace_id,
                title, message, "throttled",
            )

    notif = Notification(
        id=notif_id,
        type=template.type,
        severity=template.severity.value,
        icon=template.icon,
        title=title,
        message=message,
        fired_at=utc_now(),
        vars_payload=_json_safe(envelope.context),
        rule_id=envelope.rule_id,
    )
    row = NotificationLog(
        id=notif_id,
        trace_id=trace_id,
        template_id=template.id,
        rule_id=envelope.rule_id,
        type=template.type,
        severity=template.severity,
        title=title,
        message=message,
        vars_payload=_json_safe(envelope.context),
        context_hash=ctx_hash,
        dispatched_to=[],
        failed_channels={},
        suppressed_reason=None,
        delivery_status=DeliveryStatus.pending,
        source=envelope.source,
        is_test=envelope.test,
        fired_at=utc_now(),  # explicit UTC, not server-local (0005)
    )
    session.add(row)
    # Flush the NotificationLog first so its row exists before the
    # Delivery children reference it — there is no ORM relationship, so
    # the unit of work won't order the parent insert ahead of the FK
    # children on its own (MySQL enforces the FK; SQLite in tests does not).
    await session.flush()
    routed_overrides = {n: overrides_by_name[n] for n in channels if n in overrides_by_name}
    # Freeze the effective destination config for every channel NOW, so each
    # retry targets the same destination as this first attempt even if the
    # channel is edited meanwhile (audit V01).
    mgr = get_channel_manager()
    effective_by_name, effective_kind_by_name = await mgr.resolve_effective_configs(
        session, channels, routed_overrides,
    )
    deliveries = outbox.enqueue(
        session, notif_id, channels,
        overrides_by_name=routed_overrides,
        effective_by_name=effective_by_name,
        effective_kind_by_name=effective_kind_by_name,
    )
    # Durable intent — committed before any external effect (audit A01).
    await session.commit()

    # Synchronous first attempt (latency); retryable failures stay pending.
    # Bound it below the delivery lease (audit V03): the channel sends run in
    # parallel and are individually time-limited, but if the whole attempt
    # overruns its budget we abandon it and leave the rows pending. The lease
    # (FIRST_ATTEMPT_LEASE_SEC) is still in the future, so the worker never
    # claims a row whose first attempt is in flight; the overrun is recorded as
    # a retryable failure and retried like any transport timeout. The sends
    # touch the breaker/limiter/adapters, not this session, so cancelling them
    # leaves the session usable for the rollup below.
    started = _time.monotonic()
    # Share the outcome so a budget overrun below still carries the channels that
    # already finished — only the UNFINISHED ones are left pending, so a channel
    # that already succeeded is never re-sent on retry (audit C-04).
    outcome = DispatchOutcome()
    try:
        # On success use the returned outcome (identical object for the real
        # manager); on a budget overrun the await doesn't return, so `outcome`
        # stays the shared object the manager populated in place (C-04).
        outcome = await asyncio.wait_for(
            mgr.dispatch(
                notif, channels, session,
                overrides_by_name=routed_overrides,
                effective_by_name=effective_by_name,
                effective_kind_by_name=effective_kind_by_name,
                outcome=outcome,
            ),
            timeout=outbox.FIRST_ATTEMPT_BUDGET_SEC,
        )
    except TimeoutError:
        logger.warning(
            "first attempt for %s exceeded %ss budget; left pending for retry",
            notif_id, outbox.FIRST_ATTEMPT_BUDGET_SEC,
        )
        settled = set(outcome.succeeded) | set(outcome.failed) | set(outcome.deferred)
        for ch in channels:
            if ch not in settled:
                outcome.failed[ch] = "first attempt timed out"
    elapsed_ms = int((_time.monotonic() - started) * 1000)
    by_channel = {d.channel: d for d in deliveries}
    for ch in channels:
        d = by_channel.get(ch)
        if d is None:
            continue
        if ch in outcome.deferred:
            # Denied scheduling — reschedule without burning an attempt (F22).
            outbox.apply_deferral(d, reason=outcome.deferred[ch])
        else:
            outbox.apply_attempt(
                d, ok=ch in outcome.succeeded, error=outcome.failed.get(ch),
            )
    outbox.apply_rollup_to_log(row, deliveries)
    row.dispatch_latency_ms = elapsed_ms
    status = row.delivery_status

    from ..metrics import DISPATCH_FAILURES_TOTAL, DISPATCH_LATENCY_MS, FIRES_TOTAL
    FIRES_TOTAL.labels(
        type=template.type,
        severity=template.severity.value,
        suppressed="false",
    ).inc()
    for ch in outcome.succeeded:
        DISPATCH_LATENCY_MS.labels(channel=ch).observe(elapsed_ms)
    for ch, err in outcome.failed.items():
        DISPATCH_FAILURES_TOTAL.labels(channel=ch, reason=str(err)[:32]).inc()

    # Account the first successful delivery exactly once — template throttle AND
    # rule lifetime counter — through an idempotent CAS that a later retry shares
    # (audit V08). Gated on the persisted channel list, so a partial success
    # (one channel sent, another pending) still counts here and can't be dropped
    # or, when the pending channel later retries, double-counted.
    if not envelope.test and row.dispatched_to:
        await gating.account_first_success(row, session)

    # Release the admission claim when the fire fully FAILED, so an identical
    # retry can create a fresh notification instead of coalescing onto this
    # failed one — matching the disposition-aware dedup (audit A02/A03 × R01).
    if claimed and status == DeliveryStatus.failed:
        await release_claim(session, template.type, ctx_hash, notif_id)
    # Release the per-type cooldown reservation too (audit B-10): a fire that
    # delivered nothing must not keep the type throttled for the rest of the
    # window. A partial/full success keeps it (record_fire set last_fired_at).
    if status == DeliveryStatus.failed and template.min_repeat_min > 0 and not envelope.test:
        await gating.release_type_reservation(session, template.type, notif_id)

    return DispatchResult(
        id=notif_id,
        dispatched=status in (DeliveryStatus.sent, DeliveryStatus.partial),
        channels=outcome.succeeded,
        suppressed_reason=None,
        status=status.value,
        title=title, message=message,
        severity=template.severity.value,
    )


# ── Internals ─────────────────────────────────────────────────────


async def _load_template(session: AsyncSession, type_: str) -> Template | None:
    return (
        await session.execute(select(Template).where(Template.type == type_))
    ).scalar_one_or_none()


async def _resolve_routes(
    session: AsyncSession, template: Template,
) -> list[tuple[str, dict[str, Any] | None]]:
    """Look up routes via template_channels and return
    ``(channel.name, channel_overrides)`` pairs, filtered by
    enabled + severity_min. The per-route ``channel_overrides`` are
    merged over the channel's own config at dispatch (audit A34)."""
    rows = (
        await session.execute(
            select(
                Channel.name,
                TemplateChannel.severity_min,
                TemplateChannel.channel_overrides,
            )
            .join(TemplateChannel, TemplateChannel.channel_id == Channel.id)
            .where(
                TemplateChannel.template_id == template.id,
                TemplateChannel.enabled.is_(True),
                Channel.enabled.is_(True),
            )
        )
    ).all()
    out: list[tuple[str, dict[str, Any] | None]] = []
    for name, sev_min, overrides in rows:
        if _severity_at_least(template.severity, sev_min):
            out.append((name, overrides))
    return out


_SEV_ORDER = {Severity.info: 0, Severity.warning: 1, Severity.critical: 2}


def _severity_at_least(actual: Severity, minimum: Severity) -> bool:
    return _SEV_ORDER[actual] >= _SEV_ORDER[minimum]


async def _find_recent_dup(
    session: AsyncSession,
    envelope: FireEnvelope,
    template: Template,
    this_suppressed_reason: str | None,
) -> DispatchResult | None:
    """Return the existing log row to coalesce onto, or None.

    Window is ``Settings.idempotency_window_sec`` (default 300). A
    candidate must match (type, is_test, hash of context) AND be a
    disposition the new fire may legitimately dedup onto —
    ``delivery_status.should_coalesce`` (audit A02): a real fire never
    coalesces onto a test row, and a fire that can now be delivered is
    not masked by a stale suppressed/failed row.

    The replayed ``dispatched``/``status`` are the row's REAL settled
    outcome (audit A03): a fully-failed row replays as failed, never as
    a phantom success.
    """
    from ..config import get_settings

    h = _vars_hash(_json_safe(envelope.context))
    window_s = max(0, get_settings().idempotency_window_sec)
    if window_s == 0:
        return None
    cutoff = utc_now() - timedelta(seconds=window_s)
    # Match by the persisted context hash in SQL (indexed) so an in-window
    # duplicate is found however many distinct contexts fired meanwhile —
    # the old limit(5)+Python filter missed the 6th-oldest context (F24).
    rows = (
        await session.execute(
            select(NotificationLog)
            .where(NotificationLog.type == envelope.type)
            .where(NotificationLog.is_test.is_(bool(envelope.test)))
            .where(NotificationLog.context_hash == h)
            .where(NotificationLog.fired_at > cutoff)
            .order_by(NotificationLog.fired_at.desc())
            .limit(20)
        )
    ).scalars().all()
    for r in rows:
        if r.vars_payload is None:
            continue
        if _vars_hash(r.vars_payload) != h:
            continue
        if not should_coalesce(r, this_suppressed_reason):
            continue
        status = status_of(r)
        return DispatchResult(
            id=r.id,
            dispatched=status in (DeliveryStatus.sent, DeliveryStatus.partial),
            channels=list(r.dispatched_to or []),
            suppressed_reason=r.suppressed_reason.value if r.suppressed_reason else None,
            status=status.value,
            title=r.title, message=r.message or "",
            severity=r.severity.value,
        )
    return None


def _vars_hash(context: dict[str, Any]) -> str:
    canonical = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _current_trace() -> str:
    """Trace id for correlating a fire with the request/log that caused it
    (audit A35). Uses the request contextvar when present (HTTP /v1/fire),
    otherwise mints one so engine-originated fires are still correlatable
    and the column is never null."""
    from ..logging_setup import trace_id_var
    return trace_id_var.get() or uuid.uuid4().hex[:16]


def _generate_id() -> str:
    """A unique, bounded notification id (audit A04).

    The old ``ntf_<ms>_<type>`` scheme collided on the PRIMARY KEY when
    several fires of the same type landed in the same millisecond (12
    concurrent fires → one 500), and overflowed ``String(64)`` when the
    type was long (``Data too long for column 'id'``). The millisecond
    prefix keeps rows roughly time-sortable; the uuid4 suffix makes the
    id collision-free and type-independent. Length is a fixed 50 chars
    (``ntf_`` + 13 + ``_`` + 32), always ≤ 64.
    """
    return f"ntf_{int(_time.time() * 1000)}_{uuid.uuid4().hex}"


def _json_safe(obj: Any) -> Any:
    """Round-trip through JSON for safe storage (datetime/enum/etc.)."""
    return json.loads(json.dumps(obj, default=str))


async def _result_for_unknown_type(
    envelope: FireEnvelope, session: AsyncSession
) -> DispatchResult:
    """Caller fired a type that has no template — log a warning, write
    a notifications_log row tagged ``unknown_type`` so the operator
    can see the attempt in the audit trail, and return a synthetic
    suppressed result."""
    # Type-independent id (audit A04): the old scheme embedded the
    # caller-supplied type and overflowed String(64) for a long type.
    notif_id = f"ntf_unknown_{int(_time.time() * 1000)}_{uuid.uuid4().hex}"
    logger.warning(
        "Fire requested for unknown type %r (no template configured)",
        envelope.type,
    )

    # Persist for audit. truncate type to fit String(64).
    truncated_type = (envelope.type or "")[:64]
    row = NotificationLog(
        id=notif_id,
        trace_id=_current_trace(),
        template_id=None,
        rule_id=envelope.rule_id,
        type=truncated_type or "unknown",
        severity=Severity.info,
        title=f"(unknown type: {envelope.type})"[:255],
        message="No template registered for this notification type.",
        vars_payload=_json_safe(envelope.context),
        context_hash=_vars_hash(_json_safe(envelope.context)),
        dispatched_to=[],
        failed_channels={},
        suppressed_reason=SuppressedReason.unknown_type,
        delivery_status=DeliveryStatus.suppressed,
        source=envelope.source,
        is_test=envelope.test,
        fired_at=utc_now(),  # explicit UTC, not server-local (0005)
    )
    session.add(row)

    return DispatchResult(
        id=notif_id,
        dispatched=False,
        channels=[],
        suppressed_reason="unknown_type",
        status=DeliveryStatus.suppressed.value,
        title=f"(unknown type: {envelope.type})",
        message="No template registered for this notification type.",
        severity="info",
    )
