"""``GET /v1/log`` — paged notification history."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...db import get_session
from ...db.models import DeliveryStatus, NotificationLog, Severity
from ...schemas.common import Page
from ...schemas.common import Severity as SchemaSeverity
from ...schemas.log import LogEntryRead
from ...utils.like import like_escape
from ...utils.time import utc_now

router = APIRouter()

# Bounded at 6 digits: a window never needs to exceed ~2700 days, and an
# unbounded int overflows timedelta (audit A20: `?window=999…9d` → 500).
_WINDOW_RE = re.compile(r"^(\d{1,6})([mhd])$")
_WINDOW_UNIT = {"m": "minutes", "h": "hours", "d": "days"}


def _parse_window(window: str) -> timedelta:
    """Parse ``24h`` / ``90m`` / ``7d`` into a timedelta (≤ 6 digits)."""
    m = _WINDOW_RE.match(window.strip())
    if not m:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Bad window {window!r}; use e.g. 30m, 24h, 7d (max 6 digits).",
        )
    n = int(m.group(1))
    if n <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Bad window {window!r}; the amount must be positive.",
        )
    return timedelta(**{_WINDOW_UNIT[m.group(2)]: n})


@router.get(
    "/log",
    response_model=Page[LogEntryRead],
    summary="Query notification log",
    description=(
        "Paged log query. Filters: type, severity, suppressed (true/false), "
        "rule_id, time range (from/to ISO8601), free-text search on title."
    ),
)
async def list_log(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    type: str | None = None,
    severity: SchemaSeverity | None = None,
    suppressed: bool | None = Query(
        default=None,
        description="true → only suppressed; false → only dispatched; omit → all",
    ),
    delivery_status: str | None = Query(
        default=None,
        description="Exact settled outcome: sent | partial | failed | suppressed.",
    ),
    rule_id: int | None = None,
    acknowledged: bool | None = None,
    is_test: bool | None = Query(
        default=None, description="true → only test fires; false → only real.",
    ),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[LogEntryRead]:
    base = select(NotificationLog)
    count_q = select(func.count()).select_from(NotificationLog)
    filters = []

    if type is not None:
        filters.append(NotificationLog.type == type)
    if severity is not None:
        filters.append(NotificationLog.severity == Severity(severity.value))
    if suppressed is True:
        filters.append(NotificationLog.suppressed_reason.is_not(None))
    elif suppressed is False:
        filters.append(NotificationLog.suppressed_reason.is_(None))
    if delivery_status is not None:
        try:
            filters.append(NotificationLog.delivery_status == DeliveryStatus(delivery_status))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Bad delivery_status {delivery_status!r}; "
                       "use sent | partial | failed | suppressed.",
            ) from None
    if is_test is not None:
        filters.append(NotificationLog.is_test.is_(is_test))
    if rule_id is not None:
        filters.append(NotificationLog.rule_id == rule_id)
    if acknowledged is True:
        filters.append(NotificationLog.acknowledged_at.is_not(None))
    elif acknowledged is False:
        filters.append(NotificationLog.acknowledged_at.is_(None))
    if from_ is not None:
        filters.append(NotificationLog.fired_at >= from_)
    if to is not None:
        filters.append(NotificationLog.fired_at <= to)
    if search:
        like = f"%{like_escape(search)}%"
        filters.append(or_(
            NotificationLog.title.like(like, escape="\\"),
            NotificationLog.type.like(like, escape="\\"),
        ))

    for f in filters:
        base = base.where(f)
        count_q = count_q.where(f)

    base = base.order_by(NotificationLog.fired_at.desc()).offset(skip).limit(limit)
    rows = (await session.execute(base)).scalars().all()
    total = (await session.execute(count_q)).scalar_one()

    return Page(
        items=[LogEntryRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=skip,
    )


@router.get(
    "/log/stats",
    summary="Aggregate counters over a recent window (dashboard)",
    description=(
        "Grouped counts over the last ``window`` (e.g. 24h): dispatched vs "
        "suppressed-by-reason, by-severity, the busiest types, and the "
        "count of still-unacknowledged criticals. Indexed on fired_at."
    ),
)
async def log_stats(
    window: str = Query(default="24h", description="e.g. 30m, 24h, 7d."),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> dict:
    cutoff = utc_now() - _parse_window(window)
    recent = NotificationLog.fired_at >= cutoff

    # Delivery outcome breakdown (audit A03) — "dispatched" now means
    # actually reached ≥1 channel (sent + partial), NOT merely
    # "not suppressed", so a fully-failed fire is no longer counted
    # as a success.
    delivery_rows = (await session.execute(
        select(NotificationLog.delivery_status, func.count())
        .where(recent).group_by(NotificationLog.delivery_status)
    )).all()
    by_delivery: dict[str, int] = {}
    for d, c in delivery_rows:
        key = d.value if hasattr(d, "value") else ("unknown" if d is None else str(d))
        by_delivery[key] = by_delivery.get(key, 0) + c
    sent = by_delivery.get("sent", 0)
    partial = by_delivery.get("partial", 0)
    failed = by_delivery.get("failed", 0)
    dispatched = sent + partial

    suppressed_rows = (await session.execute(
        select(NotificationLog.suppressed_reason, func.count())
        .where(recent).where(NotificationLog.suppressed_reason.is_not(None))
        .group_by(NotificationLog.suppressed_reason)
    )).all()
    suppressed_by_reason = {
        (r.value if hasattr(r, "value") else str(r)): c for r, c in suppressed_rows
    }

    severity_rows = (await session.execute(
        select(NotificationLog.severity, func.count())
        .where(recent).group_by(NotificationLog.severity)
    )).all()
    by_severity = {
        (s.value if hasattr(s, "value") else str(s)): c for s, c in severity_rows
    }

    type_rows = (await session.execute(
        select(NotificationLog.type, func.count().label("c"))
        .where(recent).group_by(NotificationLog.type)
        .order_by(func.count().desc()).limit(10)
    )).all()
    top_types = [{"type": t, "count": c} for t, c in type_rows]

    unacked_critical = (await session.execute(
        select(func.count()).select_from(NotificationLog)
        .where(recent)
        .where(NotificationLog.severity == Severity.critical)
        .where(NotificationLog.suppressed_reason.is_(None))
        .where(NotificationLog.acknowledged_at.is_(None))
    )).scalar_one()

    return {
        "window": window,
        "since": cutoff.isoformat() + "Z",
        "dispatched": dispatched,
        "sent": sent,
        "partial": partial,
        "failed": failed,
        "by_delivery": by_delivery,
        "suppressed": sum(suppressed_by_reason.values()),
        "suppressed_by_reason": suppressed_by_reason,
        "by_severity": by_severity,
        "top_types": top_types,
        "unacked_critical": unacked_critical,
    }


@router.get(
    "/log/{notif_id}",
    response_model=LogEntryRead,
    summary="Get a single notification log entry",
    description=(
        "Used by \"why did this fire\" views to display the "
        "rule that fired, the rendered template, channel dispatch "
        "result, and the full ``vars_payload`` snapshot."
    ),
)
async def get_log_entry(
    notif_id: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> LogEntryRead:
    row = await session.get(NotificationLog, notif_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log entry not found: {notif_id}",
        )
    return LogEntryRead.model_validate(row)


@router.post(
    "/log/{notif_id}/ack",
    summary="Acknowledge a notification",
    status_code=status.HTTP_200_OK,
)
async def ack_log(
    notif_id: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("ack")),
) -> dict[str, str]:
    row = await session.get(NotificationLog, notif_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Log entry not found: {notif_id}")
    row.acknowledged_at = utc_now()
    row.acknowledged_by = actor.name
    await session.commit()
    return {"id": notif_id, "acknowledged": "ok"}
