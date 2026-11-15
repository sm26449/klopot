"""Shared fire service — every way an alert arrives goes through here.

``POST /v1/fire`` and the Alertmanager / Grafana receiver call these
functions instead of building ``FireEnvelope`` themselves, so routing,
gating, dedup and the outbox behave the same for every source.

Two shapes:

- :func:`fire` — a one-off notification (what ``/v1/fire`` always did).
- :func:`fire_episode` / :func:`resolve_episode` — a notification that
  belongs to an **external episode** (an ``incidents`` row with
  ``source_kind`` ≠ ``rule``). The episode is identified by ``source_key``
  (a caller's ``idempotency_key``, an Alertmanager fingerprint …):

  * the first firing opens the episode and notifies;
  * repeats while it is open notify nothing (Alertmanager re-sends a firing
    group every ``repeat_interval``) — escalation still runs until someone
    acknowledges. One exception: while no firing notice of the episode has
    gone out (the first was snoozed, in quiet hours, throttled, or failed
    everywhere), a repeat goes through the gates again, so an alert that
    is still firing is announced once nothing mutes it;
  * a firing with a newer ``started_at`` closes the old episode
    (``superseded``) and opens a new one;
  * a resolution closes it (stopping pending escalation) and sends the
    episode's ``resolved_template_type`` notice if it has one; a resolution
    for an older ``started_at`` than the open episode is ignored.

Acknowledgement stays a human action (``POST /v1/incidents/{id}/ack``,
Telegram buttons); a source never acknowledges.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DeliveryStatus, Incident, NotificationLog, Severity
from ..utils.text import clean_text
from ..utils.time import utc_now
from . import dispatcher, incidents, rendering
from .delivery_status import status_of

Episode = Literal["opened", "repeat", "resolved", "stale", "not_found"]


@dataclass
class EpisodeOutcome:
    episode: Episode
    incident_id: str | None = None
    # The notification sent for this call, or — for a repeat / a resolution
    # without a notice — the episode's latest one (None if there is none).
    result: dispatcher.DispatchResult | None = None


async def fire(
    session: AsyncSession, *, type: str, context: dict[str, Any], source: str | None,
    test: bool = False,
) -> dispatcher.DispatchResult:
    """A one-off notification. The caller commits."""
    return await dispatcher.fire(dispatcher.FireEnvelope(
        type=type, context=context, test=test, source=source, rule_id=None,
    ), session)


def _naive_utc(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts.replace(microsecond=0)


async def _active(session: AsyncSession, source_key: str) -> Incident | None:
    """The open episode, row-locked — or None.

    No locking read on a key that may not exist: on MySQL that takes a gap
    lock, two concurrent first fires both get one, both INSERT and deadlock
    (the whole transaction is rolled back, savepoint included). So: a plain
    read to find the row, then a lock by primary key (a record lock, which
    also returns the latest committed version — None if it was just closed).
    """
    row_id = (await session.execute(
        select(Incident.id).where(Incident.active_source_key == source_key)
    )).scalar_one_or_none()
    if row_id is None:
        return None
    return (await session.execute(
        select(Incident).where(Incident.id == row_id, Incident.active_source_key == source_key)
        .with_for_update()
    )).scalar_one_or_none()


async def _active_after_conflict(session: AsyncSession, source_key: str) -> Incident | None:
    """After losing the INSERT race the winner's row exists and is committed:
    a locking read sees it (a plain read could still serve the old snapshot)."""
    return (await session.execute(
        select(Incident).where(Incident.active_source_key == source_key).with_for_update()
    )).scalar_one_or_none()


# A firing notice counts as announced once it is out, or on its way.
_ANNOUNCED = (DeliveryStatus.sent, DeliveryStatus.partial, DeliveryStatus.pending)


async def _announced(session: AsyncSession, incident_id: str) -> bool:
    """Whether any firing notice of the episode was delivered (or is queued).

    A current read (``FOR SHARE`` on MySQL), not the transaction's snapshot
    (review K12): a concurrent repeat takes its snapshot before waiting for the
    episode row, and the dispatcher commits its notice before sending — so a
    plain read missed the notice the other repeat had just committed, and
    both announced the episode."""
    query = select(NotificationLog.id).where(
        NotificationLog.incident_id == incident_id, NotificationLog.incident_event == "firing",
        NotificationLog.delivery_status.in_(_ANNOUNCED),
    ).limit(1)
    if session.bind is not None and session.bind.dialect.name != "sqlite":
        query = query.with_for_update(read=True)
    return (await session.execute(query)).scalar_one_or_none() is not None


async def _latest(session: AsyncSession, incident_id: str, event: str) -> dispatcher.DispatchResult | None:
    log = (await session.execute(
        select(NotificationLog).where(
            NotificationLog.incident_id == incident_id, NotificationLog.incident_event == event,
        ).order_by(NotificationLog.fired_at.desc()).limit(1)
    )).scalar_one_or_none()
    if log is None:
        return None
    status = status_of(log)
    return dispatcher.DispatchResult(
        id=log.id, dispatched=status.value in ("sent", "partial"),
        channels=list(log.dispatched_to or []),
        suppressed_reason=log.suppressed_reason.value if log.suppressed_reason else None,
        status=status.value, title=log.title, message=log.message or "",
        severity=log.severity.value,
    )


async def _open(
    session: AsyncSession, *, source_kind: str, source_key: str, name: str, type: str,
    context: dict[str, Any], started_at: datetime | None, resolved_type: str | None,
) -> Incident | None:
    """Insert the episode; None if a concurrent caller opened it first."""
    template = await dispatcher._load_template(session, type)
    incident = Incident(
        id="inc_" + uuid.uuid4().hex, rule_id=None, active_rule_id=None,
        rule_name=name[:128], template_type=type, resolved_template_type=resolved_type,
        severity=template.severity if template else Severity.info,
        title=(rendering.render(template.title_template, context) if template else name)[:255],
        opened_at=utc_now().replace(microsecond=0), opening_context=dispatcher._json_safe(context),
        source_kind=source_kind, source_key=source_key, active_source_key=source_key,
        source_started_at=started_at,
    )
    try:
        async with session.begin_nested():
            session.add(incident)
            await session.flush()
    except IntegrityError:
        return None
    return incident


async def fire_episode(
    session: AsyncSession, *, source_kind: str, source_key: str, name: str, type: str,
    context: dict[str, Any], source: str | None, started_at: datetime | None = None,
    resolved_type: str | None = None,
) -> EpisodeOutcome:
    """Open (or re-confirm) the external episode ``source_key``. Caller commits.

    An unknown template type never opens an episode: the fire is logged as
    ``unknown_type`` like any other."""
    # The episode's name and title are stored from these (review K02b).
    name, type, context = clean_text(name), clean_text(type), clean_text(context)
    started = _naive_utc(started_at)
    if await dispatcher._load_template(session, type) is None:
        result = await fire(session, type=type, context=context, source=source)
        return EpisodeOutcome("opened", None, result)

    current = await _active(session, source_key)
    if current is not None:
        newer = started is not None and current.source_started_at is not None \
            and started > current.source_started_at
        if not newer:
            # Acknowledged while its first firing was muted: someone has it —
            # announcing it now would page people after the fact (review K12).
            if current.acknowledged_at is not None or await _announced(session, current.id):
                return EpisodeOutcome("repeat", current.id, await _latest(session, current.id, "firing"))
            # Nobody has heard of this episode yet: its firing was snoozed,
            # in quiet hours, throttled, or failed on every channel. The alert
            # is still firing, so let the gates decide again — otherwise it
            # stays silent for as long as it lasts.
            result = await dispatcher.fire(dispatcher.FireEnvelope(
                type=current.template_type, context=incidents._context(current, context, "firing"),
                source=source, rule_id=None, incident_id=current.id, incident_event="firing",
            ), session)
            return EpisodeOutcome("repeat", current.id, result)
        await incidents.resolve(session, current, context, reason="superseded")

    incident = await _open(
        session, source_kind=source_kind, source_key=source_key, name=name, type=type,
        context=context, started_at=started, resolved_type=resolved_type,
    )
    if incident is None:   # lost the race: someone opened it a moment ago
        current = await _active_after_conflict(session, source_key)
        return EpisodeOutcome("repeat", current.id if current else None,
                              await _latest(session, current.id, "firing") if current else None)
    result = await dispatcher.fire(dispatcher.FireEnvelope(
        type=type, context=incidents._context(incident, context, "firing"),
        source=source, rule_id=None, incident_id=incident.id, incident_event="firing",
    ), session)
    return EpisodeOutcome("opened", incident.id, result)


async def resolve_episode(
    session: AsyncSession, *, source_key: str, context: dict[str, Any],
    started_at: datetime | None = None,
) -> EpisodeOutcome:
    """Close the open episode ``source_key``. Caller commits. Idempotent:
    nothing open → ``not_found``; a resolution for an older start → ``stale``."""
    current = await _active(session, source_key)
    if current is None:
        return EpisodeOutcome("not_found")
    started = _naive_utc(started_at)
    if started is not None and current.source_started_at is not None and started < current.source_started_at:
        return EpisodeOutcome("stale", current.id)
    await incidents.resolve(session, current, context, reason="recovered")
    await session.flush()   # autoflush is off: make the resolution notice visible to _latest
    return EpisodeOutcome("resolved", current.id, await _latest(session, current.id, "resolved"))
