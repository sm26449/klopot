"""Durable rule episodes and their notification intents.

Rule locks and a nullable unique active_rule_id prevent duplicate open episodes.
Transitions and notification outbox rows commit together, before any transport.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ..db.models import (
    Delivery,
    DeliveryState,
    DeliveryStatus,
    Incident,
    NotificationLog,
    Rule,
    Severity,
)
from ..utils.time import utc_now
from . import dispatcher, gating, outbox, rendering


def lifecycle_config(rule: Rule) -> tuple[Any, ...]:
    return (
        rule.incident_enabled, rule.recovery_expr, rule.recovery_persist_n,
        rule.resolved_template_type, rule.template_type,
    )


def escalation_allowed() -> ColumnElement[bool]:
    """SQL predicate shared by the candidate scan and its conditional claim."""
    live_incident = select(Incident.id).where(
        Incident.id == NotificationLog.incident_id,
        Incident.resolved_at.is_(None), Incident.acknowledged_at.is_(None),
        NotificationLog.incident_event == "firing",
    ).exists()
    return or_(NotificationLog.incident_id.is_(None), live_incident)


async def active_incident(session: AsyncSession, rule_id: int) -> Incident | None:
    return (await session.execute(
        select(Incident).where(Incident.active_rule_id == rule_id).with_for_update()
    )).scalar_one_or_none()


async def _current_rule(session: AsyncSession, rule: Rule, epoch: int) -> Rule | None:
    current = (await session.execute(
        select(Rule).where(Rule.id == rule.id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if current is None or not current.enabled or not current.incident_enabled or current.state_epoch != epoch:
        return None
    return current


def _context(incident: Incident, values: dict[str, Any], event: str) -> dict[str, Any]:
    result = dict(values)
    result["_incident"] = {
        "id": incident.id, "rule_name": incident.rule_name, "event": event,
        "opened_at": incident.opened_at.isoformat() + "Z",
    }
    if event == "resolved":
        result["_incident"]["duration_sec"] = incident.duration_sec
    return result


async def fire_rule(
    session: AsyncSession, rule: Rule, epoch: int, context: dict[str, Any],
    inhibitor: str | None = None,
) -> dispatcher.DispatchResult | None:
    current = await _current_rule(session, rule, epoch)
    if current is None:
        return None
    incident = await active_incident(session, current.id)
    if incident is None:
        template = await dispatcher._load_template(session, current.template_type)
        incident = Incident(
            id="inc_" + uuid.uuid4().hex, rule_id=current.id, active_rule_id=current.id,
            rule_name=current.name, template_type=current.template_type,
            resolved_template_type=current.resolved_template_type,
            severity=template.severity if template else Severity.info,
            title=rendering.render(template.title_template, context)[:255] if template else current.name,
            # MySQL DATETIME has second precision. Keep metadata stable across
            # the initial commit, subsequent evaluations and process restarts.
            opened_at=utc_now().replace(microsecond=0), opening_context=dispatcher._json_safe(context),
        )
        session.add(incident)
        await session.flush()
    current.last_fired_at = utc_now()
    await session.flush()
    return await dispatcher.fire(dispatcher.FireEnvelope(
        type=current.template_type, context=_context(incident, context, "firing"),
        source="engine", rule_id=current.id, incident_id=incident.id,
        incident_event="firing", background_only=True, inhibited_by_active=inhibitor,
        acknowledged_at=incident.acknowledged_at, acknowledged_by=incident.acknowledged_by,
    ), session)


async def stop_pending(
    session: AsyncSession, incident_id: str, *, escalation_only: bool = False,
) -> None:
    """Cancel unleased firing deliveries. In-flight sends may finish."""
    now = utc_now()
    # Lock deliveries before their log rows, just like the worker. A locking
    # join could lock the log first and deadlock with an in-flight delivery.
    # Only collect logs that still have pending work, rather than loading the
    # full history of a long-lived episode into an IN clause.
    log_ids = list((await session.execute(select(NotificationLog.id).join(
        Delivery, Delivery.notification_id == NotificationLog.id,
    ).where(
        NotificationLog.incident_id == incident_id, NotificationLog.incident_event == "firing",
        Delivery.state == DeliveryState.pending,
    ).distinct())).scalars().all())
    if not log_ids:
        return
    query = select(Delivery).where(
        Delivery.notification_id.in_(log_ids),
        Delivery.state == DeliveryState.pending,
        or_(Delivery.lease_until.is_(None), Delivery.lease_until < now),
    )
    if escalation_only:
        query = query.where(Delivery.purpose == "escalation")
    # Never wait for an in-flight worker: it can be waiting to account success
    # on the rule row held by this transition. The worker rechecks resolution
    # before any subsequent retry of a skipped/expired lease.
    rows = (await session.execute(query.order_by(Delivery.id).with_for_update(skip_locked=True))).scalars().all()
    logs: set[str] = set()
    for delivery in rows:
        outbox.cancel_delivery(delivery)
        if delivery.purpose == "notification":
            logs.add(delivery.notification_id)
    await session.flush()
    for log_id in sorted(logs):
        log = await session.get(NotificationLog, log_id)
        if log is None:
            continue
        deliveries = (await session.execute(
            select(Delivery).where(Delivery.notification_id == log.id)
        )).scalars().all()
        outbox.apply_rollup_to_log(log, list(deliveries))
        if log.delivery_status in (DeliveryStatus.failed, DeliveryStatus.cancelled) and log.context_hash:
            from .dedup_claims import release_claim

            await release_claim(session, log.type, log.context_hash, log.id, test=log.is_test)
            await gating.release_type_reservation(session, log.type, log.id, test=log.is_test)


async def acknowledge(session: AsyncSession, incident: Incident, actor: str) -> None:
    if incident.acknowledged_at is None:
        incident.acknowledged_at = utc_now().replace(microsecond=0)
        incident.acknowledged_by = actor
    await session.flush()
    await session.execute(update(NotificationLog).where(
        NotificationLog.incident_id == incident.id, NotificationLog.acknowledged_at.is_(None),
    ).values(acknowledged_at=incident.acknowledged_at, acknowledged_by=incident.acknowledged_by))
    await stop_pending(session, incident.id, escalation_only=True)
    # Stop provider-side repeats (Pushover emergency receipts) — migration 0029.
    from .provider_lifecycle import enqueue_cancellations
    await enqueue_cancellations(session, incident_id=incident.id)


async def _announced(session: AsyncSession, incident: Incident) -> bool:
    """Whether anyone heard of the episode: a firing notice reached a channel,
    or is being sent now, or someone acknowledged it.

    Called after ``stop_pending``: what is still ``pending`` then is a send
    in flight (leased), not one that was just cancelled — this transaction's
    own cancellations are visible to it, so a plain read is exact."""
    if incident.acknowledged_at is not None:
        return True
    return (await session.execute(select(Delivery.id).join(
        NotificationLog, Delivery.notification_id == NotificationLog.id,
    ).where(
        NotificationLog.incident_id == incident.id, NotificationLog.incident_event == "firing",
        Delivery.state.in_((DeliveryState.sent, DeliveryState.pending)),
    ).limit(1))).scalar_one_or_none() is not None


async def resolve(
    session: AsyncSession, incident: Incident, context: dict[str, Any], *, reason: str,
) -> bool:
    """Close the episode. On recovery the ``resolved_template_type`` notice
    goes out only if the episode was announced: a recovery of a failure
    nobody heard of (snoozed, quiet hours, throttled, failed everywhere)
    would be news about nothing. The episode closes the same either way."""
    if incident.resolved_at is not None:
        return False
    incident.resolved_at = utc_now().replace(microsecond=0)
    incident.active_rule_id = None
    incident.active_source_key = None   # external episodes (migration 0028)
    incident.resolution_reason = reason
    incident.resolution_context = dispatcher._json_safe(context)
    await session.flush()
    await stop_pending(session, incident.id)
    if (reason == "recovered" and incident.resolved_template_type
            and await _announced(session, incident)):
        await dispatcher.fire(dispatcher.FireEnvelope(
            type=incident.resolved_template_type,
            context=_context(incident, context, "resolved"),
            source="engine-recovery" if incident.source_kind == "rule" else incident.source_kind,
            rule_id=incident.rule_id, incident_id=incident.id, incident_event="resolved",
            background_only=True,
        ), session)
    return True


async def recover_rule(
    session: AsyncSession, rule: Rule, epoch: int, context: dict[str, Any],
) -> bool:
    if await _current_rule(session, rule, epoch) is None:
        return False
    incident = await active_incident(session, rule.id)
    if incident is None:
        return False
    return await resolve(session, incident, context, reason="recovered")
