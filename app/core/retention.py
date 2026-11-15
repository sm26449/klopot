"""Retention task — periodically prune old log + audit rows.

Keeps the notifications_log + audit_log tables bounded so the DB
doesn't grow unbounded. Two retention windows configured separately:

- ``ALERTD_LOG_RETENTION_DAYS`` (default 90)
- ``ALERTD_AUDIT_RETENTION_DAYS`` (default 365)

Runs as a background asyncio task started in lifespan. Wakes once
per hour, deletes rows older than the cutoff, logs the count. The
once-per-hour cadence is fine — one stale day is meaningless when
operators only look at the table for incident response.

Why a Python task and not a MySQL EVENT? Two reasons:
  1. Same code ships with the service — no separate DB-side
     install steps.
  2. Lets us emit a structured log line (``retention_run``) for
     observability.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from sqlalchemy import delete, or_, select

from ..config import get_settings
from ..db import get_session_factory
from ..db.models import (
    AdminSession,
    ApiRequest,
    AuditLog,
    ChannelActionCommand,
    ChannelActionToken,
    ChannelEvent,
    ChannelProviderCommand,
    ChannelProviderMessage,
    DedupClaim,
    Delivery,
    DeliveryAttempt,
    DeliveryState,
    InboundEvent,
    Incident,
    LoginAttempt,
    NotificationLog,
    ScheduleOccurrence,
    SystemEvent,
)
from ..metrics import (
    RETENTION_LAST_RUN_TS,
    RETENTION_ROWS_DELETED_TOTAL,
    RETENTION_RUNS_TOTAL,
)
from ..utils.time import utc_now

logger = logging.getLogger(__name__)


_RUN_INTERVAL_SEC = 3600  # 1 hour


class RetentionService:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name="retention")
        logger.info("retention task started")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run(self) -> None:
        # First sweep waits 60s after boot so we don't compete with
        # migrations / seed for the connection pool.
        try:
            await asyncio.wait_for(self._stop_evt.wait(), timeout=60)
            return
        except TimeoutError:
            pass

        while not self._stop_evt.is_set():
            try:
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("retention sweep failed")
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=_RUN_INTERVAL_SEC)
                return
            except TimeoutError:
                pass

    async def _sweep(self) -> None:
        settings = get_settings()
        log_cutoff = utc_now() - timedelta(days=settings.log_retention_days)
        audit_cutoff = utc_now() - timedelta(days=settings.audit_retention_days)

        try:
            factory = get_session_factory()
            async with factory() as session:
                # Never prune a notification that still has an unresolved
                # (pending) delivery — its FK cascade would delete the queued
                # delivery and silently lose the alert if the worker is behind
                # or blocked (audit R04). Once every delivery settles
                # (sent/failed) the row becomes eligible again.
                has_pending = (
                    select(Delivery.id)
                    .where(
                        Delivery.notification_id == NotificationLog.id,
                        Delivery.state == DeliveryState.pending,
                    )
                    .exists()
                )
                has_action = select(ChannelActionCommand.id).join(
                    Delivery, ChannelActionCommand.delivery_id == Delivery.id,
                ).where(Delivery.notification_id == NotificationLog.id, ChannelActionCommand.state == "pending").exists()
                has_feedback = select(ChannelProviderCommand.id).join(
                    ChannelProviderMessage, ChannelProviderCommand.reference_id == ChannelProviderMessage.id,
                ).join(Delivery, ChannelProviderMessage.delivery_id == Delivery.id).where(
                    Delivery.notification_id == NotificationLog.id, ChannelProviderCommand.state == "pending",
                ).exists()
                has_tokens = select(ChannelActionToken.id).where(
                    ChannelActionToken.delivery_id == Delivery.id,
                ).correlate(Delivery).exists()
                materialized = select(ChannelProviderCommand.id).where(
                    ChannelProviderCommand.reference_id == ChannelProviderMessage.id,
                ).correlate(ChannelProviderMessage).exists()
                unhandled_feedback = select(ChannelProviderMessage.id).join(
                    Delivery, ChannelProviderMessage.delivery_id == Delivery.id,
                ).where(Delivery.notification_id == NotificationLog.id, has_tokens, ~materialized).exists()
                r1 = await session.execute(
                    delete(NotificationLog).where(
                        NotificationLog.fired_at < log_cutoff,
                        ~has_pending,
                        ~has_action, ~has_feedback, ~unhandled_feedback,
                    )
                )
                await session.execute(delete(ChannelEvent).where(
                    ChannelEvent.created_at < utc_now() - timedelta(days=7),
                ))
                # Generic provider inbox (0029): a receipt is never re-polled
                # after its 3 h expiry, so a week of dedup is ample.
                await session.execute(delete(InboundEvent).where(
                    InboundEvent.received_at < utc_now() - timedelta(days=7),
                ))
                r2 = await session.execute(
                    delete(AuditLog).where(AuditLog.ts < audit_cutoff)
                )
                # Keep active problems and any episode still referenced by a
                # retained notification (including pending recovery deliveries).
                has_log = select(NotificationLog.id).where(
                    NotificationLog.incident_id == Incident.id,
                ).exists()
                await session.execute(delete(Incident).where(
                    Incident.resolved_at < log_cutoff, ~has_log,
                ))
                # Prune stale admission claims (R01) — anything older than an
                # hour is well past the dedup window and would be re-claimed
                # anyway; this just bounds the table.
                await session.execute(
                    delete(DedupClaim).where(
                        DedupClaim.claimed_at < utc_now() - timedelta(hours=1)
                    )
                )
                # Prune fired-occurrence guards (V05) past the log window — the
                # matching notification is gone by then, so the guard is moot.
                await session.execute(
                    delete(ScheduleOccurrence).where(
                        ScheduleOccurrence.scheduled_at < log_cutoff
                    )
                )
                # Activity log (0032): requests expire per row (a rule can keep
                # health probes for a day); attempts and events follow the log
                # window. Deleting by an indexed column keeps this cheap.
                r_req = await session.execute(delete(ApiRequest).where(ApiRequest.expires_at < utc_now()))
                r_att = await session.execute(delete(DeliveryAttempt).where(DeliveryAttempt.started_at < log_cutoff))
                r_evt = await session.execute(delete(SystemEvent).where(SystemEvent.ts < log_cutoff))
                # Admin-UI auth history (migration 0008): old login
                # attempts and dead sessions. Live sessions are never
                # touched here — expiry is enforced at resolve time.
                auth_cutoff = utc_now() - timedelta(days=settings.auth_history_days)
                await session.execute(
                    delete(LoginAttempt).where(LoginAttempt.ts < auth_cutoff)
                )
                await session.execute(
                    delete(AdminSession).where(
                        or_(
                            AdminSession.revoked_at.is_not(None),
                            AdminSession.expires_at < utc_now(),
                        ),
                        AdminSession.last_seen_at < auth_cutoff,
                    )
                )
                await session.commit()
        except Exception:
            # Audit 2026-05-11 O-2: surface sweep failures through Prometheus
            # since INFO logs from this module don't reach stdout. Still
            # re-raise so the caller's exception handler logs the trace.
            RETENTION_RUNS_TOTAL.labels(result="error").inc()
            RETENTION_LAST_RUN_TS.set(time.time())
            raise

        log_deleted = r1.rowcount or 0
        audit_deleted = r2.rowcount or 0
        RETENTION_RUNS_TOTAL.labels(result="success").inc()
        RETENTION_ROWS_DELETED_TOTAL.labels(table="notifications_log").inc(log_deleted)
        RETENTION_ROWS_DELETED_TOTAL.labels(table="audit_log").inc(audit_deleted)
        for table, res in (("api_requests", r_req), ("delivery_attempts", r_att), ("system_events", r_evt)):
            RETENTION_ROWS_DELETED_TOTAL.labels(table=table).inc(getattr(res, "rowcount", 0) or 0)
        RETENTION_LAST_RUN_TS.set(time.time())

        logger.info(
            "retention_run",
            extra={
                "action": "retention_run",
                "log_cutoff": log_cutoff.isoformat(),
                "audit_cutoff": audit_cutoff.isoformat(),
                "log_deleted": log_deleted,
                "audit_deleted": audit_deleted,
            },
        )


_singleton: RetentionService | None = None


def get_retention_service() -> RetentionService:
    global _singleton
    if _singleton is None:
        _singleton = RetentionService()
    return _singleton
