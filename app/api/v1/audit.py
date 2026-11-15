"""``GET /v1/audit`` — paged admin-action history.

The `audit_log` table is populated by every CRUD via
``app.audit.record_change()`` (see ``app/api/v1/rules.py``,
``channels.py``, etc.). Until now there was no read-side API —
operators had to query the DB directly to see "who disabled rule
X when, with what before/after diff."

Added in 1.1.0 (audit M-3, 2026-05-14).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...db import get_session
from ...db.models import AuditLog
from ...schemas.audit import AuditLogRead
from ...schemas.common import Page

router = APIRouter()


@router.get(
    "/audit",
    response_model=Page[AuditLogRead],
    summary="Query admin action audit log",
    description=(
        "Paged audit-log query. Filters: action (e.g. 'rule.update'), "
        "resource_kind (rule / template / channel / variable / etc.), "
        "resource_id, actor_name, trace_id, time range (from/to ISO8601). "
        "Ordered by ts DESC (most recent first)."
    ),
)
async def list_audit(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    action: str | None = None,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    actor_name: str | None = None,
    trace_id: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[AuditLogRead]:
    base = select(AuditLog)
    count_q = select(func.count()).select_from(AuditLog)
    filters = []

    if action is not None:
        filters.append(AuditLog.action == action)
    if resource_kind is not None:
        filters.append(AuditLog.resource_kind == resource_kind)
    if resource_id is not None:
        filters.append(AuditLog.resource_id == resource_id)
    if actor_name is not None:
        filters.append(AuditLog.actor_name == actor_name)
    if trace_id is not None:
        filters.append(AuditLog.trace_id == trace_id)
    if from_ is not None:
        filters.append(AuditLog.ts >= from_)
    if to is not None:
        filters.append(AuditLog.ts <= to)

    if filters:
        base = base.where(*filters)
        count_q = count_q.where(*filters)

    total = (await session.execute(count_q)).scalar_one()
    rows = (
        await session.execute(
            base.order_by(AuditLog.ts.desc()).offset(skip).limit(limit)
        )
    ).scalars().all()

    return Page[AuditLogRead](
        items=[AuditLogRead.model_validate(r) for r in rows],
        total=total, limit=limit, offset=skip,
    )
