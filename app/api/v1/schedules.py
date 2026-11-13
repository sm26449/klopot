"""``/v1/schedules`` — cron-driven schedule CRUD.

Each schedule fires a template_type on its cron schedule. The
schedule service picks up changes via ``recompute_next_fire`` after
every CRUD mutation.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...config import get_settings
from ...core.schedule_service import get_schedule_service
from ...db import get_session
from ...db.models import Schedule
from ...schemas.common import Page
from ...schemas.fire import FireResponse
from ...schemas.schedule import ScheduleCreate, ScheduleRead, ScheduleUpdate
from ...utils.cron import cron_preview_local
from ...utils.time import utc_now
from ._crud import crud_get_or_404, crud_list, flush_or_409

router = APIRouter()


@router.get(
    "/preview",
    summary="Preview the next N firings of a cron expression",
    description=(
        "Validates a cron expression and returns its next ``n`` firing "
        "times in the service timezone — used by the schedule editor "
        "before saving. Pure: touches no schedule row."
    ),
)
async def preview_cron(
    cron: str = Query(..., description="5-field cron expression."),
    n: int = Query(default=5, ge=1, le=50),
    actor: Actor = Depends(require_scope("read")),
) -> dict:
    tz_name = get_settings().tz
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"
    if not croniter.is_valid(cron):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid cron expression: {cron!r}",
        )
    # Same DST-safe helper the firing runtime uses, so a previewed time
    # and the time the schedule actually fires cannot disagree (B-08).
    occurrences = cron_preview_local(cron, utc_now(), tz, n)
    out = [dt.isoformat() for dt in occurrences]
    return {"next": out, "tz": tz_name}


@router.get("", response_model=Page[ScheduleRead], summary="List schedules")
async def list_schedules(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    enabled: bool | None = None,
    template_type: str | None = None,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[ScheduleRead]:
    filters = []
    if enabled is not None:
        filters.append(Schedule.enabled.is_(enabled))
    if template_type is not None:
        filters.append(Schedule.template_type == template_type)
    items, total = await crud_list(
        session, Schedule, skip=skip, limit=limit, filters=filters,
        order_by=Schedule.name,
    )
    return Page(
        items=[ScheduleRead.model_validate(i) for i in items],
        total=total, limit=limit, offset=skip,
    )


@router.post(
    "", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED,
    summary="Create schedule",
)
async def create_schedule(
    body: ScheduleCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ScheduleRead:
    obj = Schedule(**body.model_dump())
    session.add(obj)
    await flush_or_409(session, "Schedule create")
    await session.refresh(obj)
    await record_change(
        session, actor, "schedule.create",
        resource_kind="schedule", resource_id=str(obj.id),
        after=model_to_dict(obj),
    )
    await session.commit()
    # Recompute next_fire_at from the new cron expression
    await get_schedule_service().recompute_next_fire(obj.id)
    await session.refresh(obj)
    return ScheduleRead.model_validate(obj)


@router.get("/{schedule_id}", response_model=ScheduleRead, summary="Get schedule")
async def get_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> ScheduleRead:
    obj = await crud_get_or_404(session, Schedule, schedule_id)
    return ScheduleRead.model_validate(obj)


@router.patch("/{schedule_id}", response_model=ScheduleRead, summary="Update schedule")
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ScheduleRead:
    obj = await crud_get_or_404(session, Schedule, schedule_id)
    before = model_to_dict(obj)
    cron_changed = body.cron_expr is not None and body.cron_expr != obj.cron_expr
    enabled_changed = body.enabled is not None and body.enabled != obj.enabled
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await flush_or_409(session, "Schedule update")
    await session.refresh(obj)
    await record_change(
        session, actor, "schedule.update",
        resource_kind="schedule", resource_id=str(obj.id),
        before=before, after=model_to_dict(obj),
    )
    await session.commit()
    if cron_changed or enabled_changed:
        await get_schedule_service().recompute_next_fire(obj.id)
        await session.refresh(obj)
    return ScheduleRead.model_validate(obj)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete schedule")
async def delete_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    obj = await crud_get_or_404(session, Schedule, schedule_id)
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "schedule.delete",
        resource_kind="schedule", resource_id=str(schedule_id), before=before,
    )
    await session.commit()


@router.post(
    "/{schedule_id}/test",
    response_model=FireResponse,
    summary="Fire the schedule's template once now (test=True, bypass throttle)",
)
async def test_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> FireResponse:
    from ...core import dispatcher as dispatcher_module

    obj = await crud_get_or_404(session, Schedule, schedule_id)
    envelope = dispatcher_module.FireEnvelope(
        type=obj.template_type,
        context=dict(obj.context or {}),
        test=True,
        source=f"schedule:{obj.name}:test",
    )
    result = await dispatcher_module.fire(envelope, session)
    await session.commit()
    return FireResponse(**result.as_dict())
