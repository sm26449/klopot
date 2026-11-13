"""Tests for app.core.retention — DB-backed via SQLite fixture."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, func

from app.core.retention import RetentionService
from app.db.models import AuditLog, NotificationLog, Severity, SuppressedReason


async def _seed_log_rows(session, *, count: int, age_days: int) -> None:
    fired = datetime.utcnow() - timedelta(days=age_days)
    for i in range(count):
        session.add(
            NotificationLog(
                id=f"test_{age_days}d_{i}",
                type="t",
                severity=Severity.info,
                title="hi",
                vars_payload={},
                dispatched_to=[],
                failed_channels={},
                fired_at=fired,
                source="manual",
            )
        )
    await session.commit()


async def _seed_audit_rows(session, *, count: int, age_days: int) -> None:
    from app.db.models import ActorKind

    created = datetime.utcnow() - timedelta(days=age_days)
    # SQLite doesn't auto-increment BIGINT primary keys (only the
    # exact "INTEGER PRIMARY KEY" affinity), so we supply an id
    # explicitly. Tests inject unique ids via age_days * 1000 + i.
    for i in range(count):
        session.add(
            AuditLog(
                id=age_days * 1000 + i,
                actor_kind=ActorKind.api_key,
                actor_name="t",
                action="t",
                resource_kind="t",
                resource_id=str(i),
                ts=created,
            )
        )
    await session.commit()


async def test_sweep_deletes_old_log_rows(db_session, monkeypatch):
    # Settings default log_retention_days=90
    await _seed_log_rows(db_session, count=3, age_days=120)  # old → delete
    await _seed_log_rows(db_session, count=2, age_days=10)   # fresh → keep

    svc = RetentionService()
    await svc._sweep()

    remaining = (
        await db_session.execute(select(func.count()).select_from(NotificationLog))
    ).scalar_one()
    assert remaining == 2


async def test_sweep_deletes_old_audit_rows(db_session):
    # Settings default audit_retention_days=365
    await _seed_audit_rows(db_session, count=2, age_days=400)
    await _seed_audit_rows(db_session, count=4, age_days=30)

    svc = RetentionService()
    await svc._sweep()

    remaining = (
        await db_session.execute(select(func.count()).select_from(AuditLog))
    ).scalar_one()
    assert remaining == 4


async def test_sweep_keeps_old_log_with_pending_delivery(db_session):
    """R04: an old notification that still has a pending delivery must NOT be
    pruned (the FK cascade would lose the queued alert); once its deliveries
    settle it becomes eligible again."""
    from app.db.models import Delivery, DeliveryState

    old = datetime.utcnow() - timedelta(days=120)
    for nid in ("old_pending", "old_sent"):
        db_session.add(NotificationLog(
            id=nid, type="t", severity=Severity.info, title="hi",
            vars_payload={}, dispatched_to=[], failed_channels={},
            fired_at=old, source="m",
        ))
    await db_session.commit()
    db_session.add(Delivery(
        notification_id="old_pending", channel="ui",
        state=DeliveryState.pending, attempts=0, idempotency_key="old_pending:ui",
    ))
    db_session.add(Delivery(
        notification_id="old_sent", channel="ui",
        state=DeliveryState.sent, attempts=1, idempotency_key="old_sent:ui",
    ))
    await db_session.commit()

    await RetentionService()._sweep()

    ids = set(
        (await db_session.execute(select(NotificationLog.id))).scalars().all()
    )
    assert "old_pending" in ids      # kept — unresolved delivery
    assert "old_sent" not in ids     # pruned — fully settled


async def test_sweep_no_op_on_fresh_db(db_session):
    """Empty tables should sweep cleanly without errors."""
    svc = RetentionService()
    await svc._sweep()
    assert (
        (await db_session.execute(select(func.count()).select_from(NotificationLog)))
        .scalar_one() == 0
    )


async def test_singleton_returns_same_instance():
    from app.core.retention import get_retention_service

    a = get_retention_service()
    b = get_retention_service()
    assert a is b


async def test_start_stop_lifecycle(db_engine):
    """start() spawns a background task; stop() cancels it cleanly."""
    svc = RetentionService()
    await svc.start()
    assert svc._task is not None
    await svc.stop()
    assert svc._task is None


async def test_start_idempotent(db_engine):
    svc = RetentionService()
    await svc.start()
    task = svc._task
    await svc.start()  # second call is a no-op
    assert svc._task is task
    await svc.stop()


async def test_sweep_increments_prometheus_counters(db_session):
    """Audit 2026-05-11 O-2: retention sweep must surface through
    Prometheus so absence is visible even when stdout logging is muted.
    """
    from app.metrics import (
        RETENTION_LAST_RUN_TS,
        RETENTION_ROWS_DELETED_TOTAL,
        RETENTION_RUNS_TOTAL,
    )

    runs_before = RETENTION_RUNS_TOTAL.labels(result="success")._value.get()
    log_deleted_before = (
        RETENTION_ROWS_DELETED_TOTAL.labels(table="notifications_log")._value.get()
    )
    audit_deleted_before = (
        RETENTION_ROWS_DELETED_TOTAL.labels(table="audit_log")._value.get()
    )

    await _seed_log_rows(db_session, count=2, age_days=120)
    await _seed_audit_rows(db_session, count=3, age_days=400)
    svc = RetentionService()
    await svc._sweep()

    runs_after = RETENTION_RUNS_TOTAL.labels(result="success")._value.get()
    log_after = (
        RETENTION_ROWS_DELETED_TOTAL.labels(table="notifications_log")._value.get()
    )
    audit_after = (
        RETENTION_ROWS_DELETED_TOTAL.labels(table="audit_log")._value.get()
    )
    last_ts = RETENTION_LAST_RUN_TS._value.get()

    assert runs_after == runs_before + 1
    assert log_after == log_deleted_before + 2
    assert audit_after == audit_deleted_before + 3
    assert last_ts > 0


async def test_sweep_failure_increments_error_counter(db_session, monkeypatch):
    """Failures bump the result=error counter and still update the
    last-run timestamp so a stuck/crashing sweep is visible in Grafana.
    """
    from app.metrics import RETENTION_RUNS_TOTAL

    errs_before = RETENTION_RUNS_TOTAL.labels(result="error")._value.get()

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated DB failure")

    # Replace the session factory with one that explodes on first use
    import app.core.retention as ret

    monkeypatch.setattr(ret, "get_session_factory", _boom)

    svc = RetentionService()
    with pytest.raises(RuntimeError, match="simulated DB failure"):
        await svc._sweep()

    errs_after = RETENTION_RUNS_TOTAL.labels(result="error")._value.get()
    assert errs_after == errs_before + 1
