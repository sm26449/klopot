"""Async gating pipeline — decides whether a fire actually dispatches.

Each gate is a pure function over (template, envelope, db_session)
returning either ``allow(channels)`` or ``deny(reason)``. The
dispatcher chains them in priority order; first deny wins.

Order:

1. ``enabled``     — template flipped off in admin UI
2a. ``snoozed``    — type / rule mute (deny outright)
2b. ``snoozed``    — channel mute (strips those destinations; deny
                     ``snoozed`` only if every channel is stripped)
3. ``throttled``   — last fire within ``min_repeat_min``
4. ``quiet_hours`` — strips channels muted by the template's per-channel
                     windows OR the channel's own ``quiet_hours`` (audit
                     A05); if all stripped, treat as ``gated``. Evaluated
                     in the service timezone.

``persist`` is enforced by the ENGINE via ``rule_state`` counters
(it's a property of the rule, not of the dispatch). ``test=True``
on a fire envelope bypasses 3 + 4 (the silencing gates) but still
respects 1 + 2.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    Channel,
    NotificationLog,
    Rule,
    Snooze,
    SnoozeScope,
    Template,
    ThrottleState,
)
from ..utils.time import utc_now

logger = logging.getLogger(__name__)


@dataclass
class GateDecision:
    """Output of the gating pipeline."""

    allowed: bool
    channels: list[str] = field(default_factory=list)
    reason: str | None = None

    @classmethod
    def deny(cls, reason: str) -> GateDecision:
        return cls(allowed=False, channels=[], reason=reason)

    @classmethod
    def allow(cls, channels: list[str]) -> GateDecision:
        return cls(allowed=True, channels=list(channels), reason=None)


@dataclass
class GateInput:
    """Everything a gate needs to decide. Kept small for testability."""

    template: Template
    rule_id: int | None
    channel_names: list[str]
    test: bool = False


# ── Public entry point ────────────────────────────────────────────


async def evaluate(g: GateInput, session: AsyncSession) -> GateDecision:
    """Run all gates in priority order. First deny wins."""

    # 1. enabled
    if not g.template.enabled:
        return GateDecision.deny("disabled")

    # 2a. snooze, type / rule scope — deny outright
    if await _any_active_snooze(g, session):
        return GateDecision.deny("snoozed")

    # 2b. snooze, channel scope — strip the muted destinations (audit
    # A05: these were accepted but never applied). Snooze is respected
    # by test fires too (it's a gate-2 mute, not a silencing gate).
    channels = list(g.channel_names)
    snoozed = await _snoozed_channels(channels, session)
    if snoozed:
        channels = [c for c in channels if c not in snoozed]
        if not channels:
            return GateDecision.deny("snoozed")

    # Test fires skip the silencing gates 3 + 4 but still respect 1 + 2
    if not g.test:
        # 3. throttle
        if await _is_throttled(g.template, session):
            return GateDecision.deny("throttled")

        # 3b. PV-power gate (audit A34) — a template may require a minimum
        # current power before its alert is relevant. Full-fire deny.
        if _pv_power_below_threshold(g.template):
            return GateDecision.deny("pv_power")

        # 4. quiet hours — strip channels muted by the template's
        # per-channel windows AND each channel's OWN quiet_hours (audit
        # A05: Channel.quiet_hours was ignored). Evaluated in the
        # service timezone, not server-local (docs/EDGE_CASES.md).
        channel_quiet = await _load_channel_quiet(channels, session)
        if g.template.quiet_hours or channel_quiet:
            channels = _strip_quiet_channels(
                channels, g.template.quiet_hours, channel_quiet
            )

    if not channels:
        return GateDecision.deny("gated")

    return GateDecision.allow(channels)


# ── Snooze ────────────────────────────────────────────────────────


async def _any_active_snooze(g: GateInput, session: AsyncSession) -> bool:
    """True if an active snooze covers this template type or this rule.

    Type and rule scope deny the whole fire outright. Channel-scope
    snoozes are handled separately by ``_snoozed_channels`` (they strip
    individual destinations rather than denying), so they are NOT
    considered here.
    """
    now = utc_now()

    # type — target "*" is MAINTENANCE MODE: one snooze row mutes
    # every template until it expires (physical work on the plant).
    # Created via POST /v1/snooze {"scope":"type","target":"*",...}.
    row = (
        await session.execute(
            select(Snooze.id).where(
                Snooze.scope == SnoozeScope.type,
                Snooze.target.in_([g.template.type, "*"]),
                Snooze.until > now,
            ).limit(1)
        )
    ).first()
    if row is not None:
        return True

    # rule
    if g.rule_id is not None:
        row = (
            await session.execute(
                select(Snooze.id).where(
                    Snooze.scope == SnoozeScope.rule,
                    Snooze.target == str(g.rule_id),
                    Snooze.until > now,
                ).limit(1)
            )
        ).first()
        if row is not None:
            return True

    return False


async def _snoozed_channels(
    channels: list[str], session: AsyncSession
) -> set[str]:
    """Names (⊆ ``channels``) with an active ``channel``-scope snooze."""
    if not channels:
        return set()
    now = utc_now()
    rows = (
        await session.execute(
            select(Snooze.target).where(
                Snooze.scope == SnoozeScope.channel,
                Snooze.target.in_(channels),
                Snooze.until > now,
            )
        )
    ).scalars().all()
    return set(rows)


# ── PV-power gate (audit A34) ─────────────────────────────────────


def _pv_power_below_threshold(template: Template) -> bool:
    """True when the template declares ``require_pv_kw`` and the current
    power (read from the configured state-cache variable) is below it.

    Fail-open by design: if the gate isn't configured (no variable name),
    or the variable is absent / null / stale / non-numeric, we return
    False so a real alert is never suppressed on a data gap. The service
    stays domain-agnostic — it only knows a variable name and a threshold.
    """
    from ..config import get_settings
    from .state_cache import get_state_cache

    threshold = template.require_pv_kw
    if threshold is None:
        return False
    var_name = get_settings().pv_power_var
    if not var_name:
        return False
    snap = get_state_cache().get(var_name)
    if snap is None or snap.value is None or snap.is_stale():
        return False
    try:
        current = float(snap.value)
    except (TypeError, ValueError):
        return False
    return current < threshold


# ── Throttle ──────────────────────────────────────────────────────


async def _is_throttled(template: Template, session: AsyncSession) -> bool:
    """True if last fire is within ``template.min_repeat_min`` of now."""
    if template.min_repeat_min <= 0:
        return False
    row = (
        await session.execute(
            select(ThrottleState.last_fired_at).where(ThrottleState.type == template.type)
        )
    ).first()
    if row is None or row[0] is None:
        return False
    last = row[0] if isinstance(row[0], datetime) else None
    if last is None:
        return False
    elapsed_s = (utc_now() - last).total_seconds()
    return elapsed_s < (template.min_repeat_min * 60)


async def record_fire(type_: str, session: AsyncSession) -> None:
    """Update last_fired_at after a successful (non-suppressed)
    dispatch. Caller commits.

    Race condition fix (audit C-6, 2026-05-14): the previous
    UPDATE-then-INSERT pattern was non-atomic in MySQL. Two
    simultaneous fires of the same ``type_`` (engine + schedule
    + manual /fire racing on the same template) would both see
    rowcount==0 on the initial UPDATE, both ``session.add()`` a
    new row, and the second commit would IntegrityError on the
    PRIMARY KEY of throttle_state.type — losing one throttle
    update and letting the next fire come through ungated.

    The MySQL ``INSERT ... ON DUPLICATE KEY UPDATE`` is atomic
    at the row level (locks the unique index entry), so two
    concurrent calls serialise correctly with no exception.

    SQLite (test suite) has no ON DUPLICATE KEY; its native
    ``INSERT ... ON CONFLICT DO UPDATE`` has the same row-level
    atomic upsert semantics, so we branch on the bound dialect.
    """
    now = utc_now()
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(ThrottleState).values(
            type=type_, last_fired_at=now,
        ).on_conflict_do_update(
            index_elements=[ThrottleState.type],
            set_={"last_fired_at": now},
        )
    else:
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        stmt = mysql_insert(ThrottleState).values(
            type=type_, last_fired_at=now,
        ).on_duplicate_key_update(last_fired_at=now)
    await session.execute(stmt)


async def reserve_type_slot(
    session: AsyncSession, type_: str, notif_id: str,
    now: datetime, cutoff: datetime,
) -> str | None:
    """Atomically reserve the per-type cooldown slot at admission (audit B-10).

    The success-anchored throttle (``_is_throttled`` / ``last_fired_at``) cannot
    serialise two *distinct-context* fires that race before either has
    succeeded, so both pass and both send despite ``min_repeat_min``. This takes
    an admission-anchored reservation in the durable-intent transaction: the
    slot is held while EITHER the in-flight ``reserved_at`` OR the confirmed
    ``last_fired_at`` is newer than ``cutoff`` (``now - min_repeat`` window), so
    the reservation and the confirmed cooldown share one boundary.

    Returns the ``notification_id`` that holds the slot — this fire won iff the
    return equals ``notif_id``. The conditional upsert overwrites only a *free*
    slot (both timestamps older than ``cutoff``), so concurrent fires resolve to
    a single winner the same way :func:`dedup_claims.claim_fire` does. The slot
    is released on terminal failure and superseded by ``record_fire`` on success.
    """
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    free = and_(
        or_(ThrottleState.reserved_at.is_(None), ThrottleState.reserved_at < cutoff),
        or_(ThrottleState.last_fired_at.is_(None), ThrottleState.last_fired_at < cutoff),
    )
    values = {"type": type_, "reserved_at": now, "reserved_by": notif_id}
    # Dialect-conditional claim. The sqlite and mysql Insert constructs are
    # distinct types with dialect-only methods, so each branch runs its own
    # statement(s).
    stmt: Any
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        # One atomic upsert whose WHERE gates the whole claim on `free`.
        stmt = sqlite_insert(ThrottleState).values(**values).on_conflict_do_update(
            index_elements=["type"],
            set_={"reserved_at": now, "reserved_by": notif_id},
            where=free,
        )
        await session.execute(stmt)
    else:
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        # MySQL's ON DUPLICATE KEY UPDATE has no WHERE and evaluates its SET
        # assignments left to right, each seeing the earlier ones' result — so a
        # per-column `CASE(free)` that updates reserved_at first corrupts the
        # `free` test for reserved_by, and a slot freed by a release is never
        # re-claimed (audit B-10, MySQL-only bug). Do it atomically in two steps:
        # ensure the row exists (which claims it on the first fire), then claim a
        # stale slot with a WHERE-guarded UPDATE that no-ops for a losing fire.
        ensure = mysql_insert(ThrottleState).values(**values)
        ensure = ensure.on_duplicate_key_update(reserved_by=ThrottleState.reserved_by)
        await session.execute(ensure)
        await session.execute(
            update(ThrottleState)
            .where(ThrottleState.type == type_, free)
            .values(reserved_at=now, reserved_by=notif_id)
        )

    # Read the winning holder back with a CURRENT read (FOR UPDATE on MySQL), for
    # the same REPEATABLE-READ-snapshot reason as claim_fire: the loser of a true
    # race must see the winner's just-committed row, not a stale snapshot.
    sel = select(ThrottleState.reserved_by).where(ThrottleState.type == type_)
    if dialect != "sqlite":
        sel = sel.with_for_update()
    return (await session.execute(sel)).scalar_one_or_none()


async def release_type_reservation(
    session: AsyncSession, type_: str, notif_id: str,
) -> None:
    """Release this fire's per-type cooldown reservation (only if it still holds
    it), so a terminally-failed fire that delivered nothing does not keep the
    type throttled for the rest of the window (audit B-10)."""
    await session.execute(
        update(ThrottleState)
        .where(ThrottleState.type == type_, ThrottleState.reserved_by == notif_id)
        .values(reserved_at=None, reserved_by=None)
    )


async def account_first_success(
    log: NotificationLog, session: AsyncSession
) -> bool:
    """Account a notification's first successful delivery, exactly once.

    A fire is "counted" when at least one of its channels has delivered. That
    first success may land synchronously (the dispatcher) or on a later retry
    (the delivery worker), and a partial success (one channel sent, another
    still pending) leaves the rollup ``pending`` — so neither the channel list
    nor the rollup status is a sound "already counted?" flag (audit V08). This
    helper flips ``success_counted`` with a compare-and-set: the first caller to
    win the CAS performs the accounting (template throttle + rule lifetime
    counter); every later caller is a no-op. Caller commits.

    Returns True iff this call won the race and performed the accounting.
    """
    won = (
        await session.execute(
            update(NotificationLog)
            .where(
                NotificationLog.id == log.id,
                NotificationLog.success_counted.is_(False),
            )
            .values(success_counted=True)
        )
    ).rowcount == 1
    if not won:
        return False
    log.success_counted = True
    await record_fire(log.type, session)
    if log.rule_id is not None:
        await session.execute(
            update(Rule)
            .where(Rule.id == log.rule_id)
            .values(fire_count_lifetime=Rule.fire_count_lifetime + 1)
        )
    return True


# ── Quiet hours ───────────────────────────────────────────────────


async def _load_channel_quiet(
    channels: list[str], session: AsyncSession
) -> dict[str, Any]:
    """Map channel name → its own ``quiet_hours`` config (only non-empty
    ones), for the routed channels (audit A05)."""
    if not channels:
        return {}
    rows = (
        await session.execute(
            select(Channel.name, Channel.quiet_hours).where(
                Channel.name.in_(channels)
            )
        )
    ).all()
    return {name: qh for name, qh in rows if qh}


def _tz_now_time() -> time:
    """Current wall-clock time in the service timezone (not server-local
    — docs/EDGE_CASES.md: quiet hours are evaluated in ``settings.tz`` so
    two operators see the same outcome).

    Audit F14: the field is ``tz``, not ``timezone``; the old lookup
    raised AttributeError which a broad ``except`` silently turned into a
    UTC fallback, so quiet hours were always evaluated in UTC. Only an
    unknown tz NAME falls back now."""
    from zoneinfo import ZoneInfoNotFoundError

    from ..config import get_settings

    try:
        tz = ZoneInfo(get_settings().tz)
    except (ZoneInfoNotFoundError, ValueError):  # pragma: no cover
        tz = ZoneInfo("UTC")
    return datetime.now(tz).time()


def _channel_window(quiet_hours: Any) -> str | None:
    """Extract a channel's own quiet window string from its stored
    ``quiet_hours``. Contract: ``{"window": "22-07"}`` (a bare string is
    also accepted). Anything else → no window."""
    if not quiet_hours:
        return None
    if isinstance(quiet_hours, str):
        return quiet_hours
    if isinstance(quiet_hours, dict):
        w = quiet_hours.get("window")
        return w if isinstance(w, str) else None
    return None


def _strip_quiet_channels(
    channels: list[str],
    quiet_hours: dict[str, Any] | None,
    channel_quiet: dict[str, Any] | None = None,
    now_t: time | None = None,
) -> list[str]:
    """Drop channels muted right now by the template's per-channel
    windows (``quiet_hours[name]``) OR the channel's own quiet window
    (``Channel.quiet_hours``). Evaluated in the service timezone."""
    if now_t is None:
        now_t = _tz_now_time()
    template_q = quiet_hours or {}
    channel_q = channel_quiet or {}
    out: list[str] = []
    for c in channels:
        if _in_quiet_window(now_t, template_q.get(c)):
            continue
        if _in_quiet_window(now_t, _channel_window(channel_q.get(c))):
            continue
        out.append(c)
    return out


# Track which malformed quiet windows we've already warned about so the
# log doesn't drown when a single config error fires every 10 s.
_QUIET_WARNED: set[str] = set()


def _parse_hhmm(raw: str) -> time:
    """Parse ``"22"`` → 22:00; ``"22:30"`` → 22:30. Raises ValueError on bad input."""
    raw = raw.strip()
    if ":" in raw:
        h_str, m_str = raw.split(":", 1)
        return time(int(h_str), int(m_str))
    return time(int(raw))


def _in_quiet_window(now: time, window: str | None) -> bool:
    """Window like ``"22-07"`` or ``"22:30-07:00"`` (crosses midnight)."""
    if not window:
        return False
    if not isinstance(window, str):
        # Defensive: a non-string window (e.g. a stale/malformed config) must
        # fail open, not raise AttributeError on .split (audit F29).
        return False
    try:
        start_str, end_str = window.split("-")
        start = _parse_hhmm(start_str)
        end = _parse_hhmm(end_str)
    except (ValueError, IndexError):
        # Malformed — fail open, but warn once so the operator sees it.
        if window not in _QUIET_WARNED:
            _QUIET_WARNED.add(window)
            logger.warning(
                "quiet_hours window %r is malformed (expected 'HH-HH' or 'HH:MM-HH:MM'); "
                "ignoring (fail-open) until config is corrected", window,
            )
        return False
    if start <= end:
        return start <= now < end
    # Crosses midnight: 22:00 → 07:00 means [22:00, 24:00) ∪ [00:00, 07:00)
    return now >= start or now < end
