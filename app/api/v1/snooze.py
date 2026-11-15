"""``/v1/snooze`` — temporary-mute CRUD.

The Snooze model + SnoozeScope have lived in ``db/models.py`` and
``core/gating.py`` since v1.0.0 — the gate honors any row whose
``until`` is in the future for the target ``(scope, target)`` pair.
This module exposes the CRUD endpoints behind the UI's snooze
controls.

Added in v1.3.0 (audit L-7, 2026-05-15).
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...db import get_session
from ...db.models import Snooze, SnoozeScope
from ...schemas.common import Page
from ...schemas.snooze import SnoozeCreate, SnoozeRead
from ...utils.time import to_naive_utc
from ._crud import flush_or_409

router = APIRouter()


@router.get(
    "",
    response_model=Page[SnoozeRead],
    summary="List active or all snoozes",
    description=(
        "Paged list. ``active=true`` (default) filters to entries "
        "whose ``until > now``. Filter by ``scope`` (type/rule/channel) "
        "and ``target`` to drill down."
    ),
)
async def list_snoozes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    scope: str | None = Query(default=None),
    target: str | None = Query(default=None),
    active: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[SnoozeRead]:
    base = select(Snooze)
    count_q = select(func.count()).select_from(Snooze)
    filters = []
    if scope is not None:
        try:
            filters.append(Snooze.scope == SnoozeScope(scope))
        except ValueError:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope: {scope}. Use type/rule/channel.",
            ) from None
    if target is not None:
        filters.append(Snooze.target == target)
    if active:
        filters.append(Snooze.until > datetime.now(UTC))
    if filters:
        base = base.where(*filters)
        count_q = count_q.where(*filters)

    total = (await session.execute(count_q)).scalar_one()
    rows = (
        await session.execute(
            base.order_by(Snooze.until.desc()).offset(skip).limit(limit)
        )
    ).scalars().all()
    return Page[SnoozeRead](
        items=[SnoozeRead.model_validate(r) for r in rows],
        total=total, limit=limit, offset=skip,
    )


@router.post(
    "",
    response_model=SnoozeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a snooze",
)
async def create_snooze(
    body: SnoozeCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("ack")),
) -> SnoozeRead:
    # Compare in UTC (treat a naive input as UTC), then store as naive-UTC
    # so an offset-bearing `until` isn't persisted as wall-clock (F15).
    until = body.until if body.until.tzinfo else body.until.replace(tzinfo=UTC)
    if until <= datetime.now(UTC):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="`until` must be in the future",
        )
    # A rule-scope snooze is matched by rule ID in gating, so the target
    # MUST be a valid rule id — reject a name/unknown id loudly instead of
    # silently never muting the rule (audit F16).
    if body.scope == "rule":
        from ...db.models import Rule
        if not body.target.isdigit() or await session.get(Rule, int(body.target)) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"rule snooze target must be an existing rule id (got {body.target!r})",
            )
    obj = Snooze(
        scope=SnoozeScope(body.scope),
        target=body.target,
        until=to_naive_utc(until),
        reason=body.reason,
        created_by=actor.name,
    )
    session.add(obj)
    await flush_or_409(session, "Snooze create")
    await session.refresh(obj)
    await record_change(
        session, actor, "snooze.create",
        resource_kind="snooze", resource_id=str(obj.id),
        after=model_to_dict(obj),
    )
    await session.commit()
    return SnoozeRead.model_validate(obj)


@router.delete(
    "/{snooze_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a snooze",
)
async def delete_snooze(
    snooze_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("ack")),
):
    obj = (
        await session.execute(select(Snooze).where(Snooze.id == snooze_id))
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Snooze not found")
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "snooze.delete",
        resource_kind="snooze", resource_id=str(snooze_id),
        before=before,
    )
    await session.commit()
