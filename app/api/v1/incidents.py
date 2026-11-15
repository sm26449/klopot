"""Read and operate on durable incidents without confusing ack and resolution."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...core import incidents
from ...db import get_session
from ...db.models import Incident, Rule, RuleState
from ...schemas.common import Page
from ...schemas.incident import IncidentDetail, IncidentRead, ResolveIncidentRequest
from ...utils.like import like_escape
from ._crud import crud_get_or_404, crud_list

router = APIRouter()


@router.get("", response_model=Page[IncidentRead])
async def list_incidents(
    state: Literal["active", "resolved"] | None = None,
    acknowledged: bool | None = None,
    rule_id: int | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[IncidentRead]:
    filters: list[ColumnElement[bool]] = []
    if state == "active":
        filters.append(Incident.resolved_at.is_(None))
    elif state == "resolved":
        filters.append(Incident.resolved_at.is_not(None))
    if acknowledged is not None:
        filters.append(Incident.acknowledged_at.is_not(None) if acknowledged else Incident.acknowledged_at.is_(None))
    if rule_id is not None:
        filters.append(Incident.rule_id == rule_id)
    if search:
        pattern = f"%{like_escape(search)}%"
        filters.append(or_(Incident.rule_name.like(pattern, escape="\\"), Incident.title.like(pattern, escape="\\")))
    items, total = await crud_list(
        session, Incident, skip=skip, limit=limit, filters=filters,
        order_by=(Incident.opened_at.desc(), Incident.id.desc()),
    )
    return Page(items=[IncidentRead.model_validate(i) for i in items], total=total, limit=limit, offset=skip)


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: str, session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> IncidentDetail:
    return IncidentDetail.model_validate(await crud_get_or_404(session, Incident, incident_id))


async def locked_incident(session: AsyncSession, incident_id: str) -> Incident:
    incident = (await session.execute(
        select(Incident).where(Incident.id == incident_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("/{incident_id}/ack", response_model=IncidentDetail)
async def ack_incident(
    incident_id: str, session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("ack")),
) -> IncidentDetail:
    incident = await locked_incident(session, incident_id)
    before = model_to_dict(incident)
    if incident.acknowledged_at is None:
        await incidents.acknowledge(session, incident, actor.name)
        await record_change(session, actor, "incident.ack", resource_kind="incident", resource_id=incident.id,
                            before=before, after=model_to_dict(incident))
    await session.commit()
    return IncidentDetail.model_validate(incident)


@router.post("/{incident_id}/resolve", response_model=IncidentDetail)
async def resolve_incident(
    incident_id: str, body: ResolveIncidentRequest,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("ack")),
) -> IncidentDetail:
    snapshot = await crud_get_or_404(session, Incident, incident_id)
    # Match the engine's lock order: rule, then incident. Manual resolution
    # starts a fresh persistence streak if the problem subsequently reappears.
    rule = (await session.execute(
        select(Rule).where(Rule.id == snapshot.rule_id).with_for_update()
    )).scalar_one_or_none() if snapshot.rule_id else None
    incident = await locked_incident(session, incident_id)
    before = model_to_dict(incident)
    if incident.resolved_at is None and rule is not None:
        rule.state_epoch += 1
        runtime_state = await session.get(RuleState, rule.id)
        if runtime_state is not None:
            runtime_state.consecutive_match_count = 0
            runtime_state.recovery_match_count = 0
            runtime_state.state_epoch = rule.state_epoch
    if await incidents.resolve(session, incident, {}, reason=f"manual: {body.reason.strip()}"):
        await record_change(session, actor, "incident.resolve", resource_kind="incident", resource_id=incident.id,
                            before=before, after=model_to_dict(incident))
    await session.commit()
    if rule is not None:
        from ...core.engine import get_engine

        await get_engine().reload_rules()
    return IncidentDetail.model_validate(incident)
