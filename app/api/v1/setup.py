"""``/v1/setup`` — what a new installation still needs (the setup guide).

Every step is derived from the live configuration, never ticked by hand, so
the guide stays honest when things are configured through the API or a pack.
Hiding the guide is an audit event (``setup.dismiss`` / ``setup.reopen``) —
it needs no schema of its own and records who did it.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import record_change
from ...auth import Actor, require_scope
from ...config import get_settings
from ...db.models import (
    ApiKey,
    AuditLog,
    Channel,
    Delivery,
    DeliveryState,
    Input,
    NotificationLog,
    Rule,
    Template,
)
from ...db.session import get_session

router = APIRouter()

# Channels every install has; they show alerts in the admin UI only.
BUILT_IN_CHANNEL_KINDS = frozenset({"ui", "banner"})
# Templates every install has (the self-monitoring pack).
BUILT_IN_CATEGORY = "Self-monitoring"

StepId = Literal["channel", "channel_tested", "source", "rules", "first_alert"]


class SetupStep(BaseModel):
    id: StepId
    done: bool
    count: int = Field(description="How many items satisfy the step (channels, inputs + keys, rules…).")


class SetupStatus(BaseModel):
    complete: bool = Field(description="Every step is done.")
    dismissed: bool = Field(description="An admin hid the guide (POST /v1/setup/dismiss); reopen brings it back.")
    timezone: str = Field(description="ALERTD_TZ — quiet hours, schedules and the digest use it.")
    steps: list[SetupStep]


async def _count(session: AsyncSession, stmt) -> int:  # type: ignore[no-untyped-def]
    return int((await session.execute(stmt)).scalar_one() or 0)


async def compute_status(session: AsyncSession) -> SetupStatus:
    channels = (await session.execute(select(Channel.name, Channel.kind, Channel.enabled))).all()
    external = [name for name, kind, enabled in channels
                if enabled and getattr(kind, "value", kind) not in BUILT_IN_CHANNEL_KINDS]

    tested_ok = 0
    for (after,) in (await session.execute(
            select(AuditLog.after).where(AuditLog.action == "channel.test"))).all():
        if isinstance(after, dict) and after.get("ok") and after.get("channel") in external:
            tested_ok += 1
    if external:
        tested_ok += await _count(session, select(func.count()).select_from(Delivery).where(
            Delivery.channel.in_(external), Delivery.state == DeliveryState.sent))

    inputs = await _count(session, select(func.count()).select_from(Input))
    keys = (await session.execute(select(ApiKey.scopes, ApiKey.enabled))).all()
    fire_keys = sum(1 for scopes, enabled in keys if enabled and "fire" in (scopes or []))

    rules = await _count(session, select(func.count()).select_from(Rule))
    own_templates = await _count(session, select(func.count()).select_from(Template).where(
        (Template.category.is_(None)) | (Template.category != BUILT_IN_CATEGORY)))
    alerts = await _count(session, select(func.count()).select_from(NotificationLog))

    steps = [
        SetupStep(id="channel", done=bool(external), count=len(external)),
        SetupStep(id="channel_tested", done=tested_ok > 0, count=tested_ok),
        SetupStep(id="source", done=inputs + fire_keys > 0, count=inputs + fire_keys),
        SetupStep(id="rules", done=rules + own_templates > 0, count=rules + own_templates),
        SetupStep(id="first_alert", done=alerts > 0, count=alerts),
    ]
    last = (await session.execute(
        select(AuditLog.action).where(AuditLog.action.in_(("setup.dismiss", "setup.reopen")))
        .order_by(AuditLog.id.desc()).limit(1))).scalar_one_or_none()
    return SetupStatus(
        complete=all(s.done for s in steps), dismissed=last == "setup.dismiss",
        timezone=get_settings().tz, steps=steps,
    )


@router.get("/status", response_model=SetupStatus, summary="What this installation still needs")
async def setup_status(
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> SetupStatus:
    return await compute_status(session)


async def _mark(session: AsyncSession, actor: Actor, action: str) -> SetupStatus:
    await record_change(session, actor, action, resource_kind="setup", resource_id="guide")
    await session.commit()
    return await compute_status(session)


@router.post("/dismiss", response_model=SetupStatus, summary="Hide the setup guide")
async def dismiss(
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> SetupStatus:
    return await _mark(session, actor, "setup.dismiss")


@router.post("/reopen", response_model=SetupStatus, summary="Show the setup guide again")
async def reopen(
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> SetupStatus:
    return await _mark(session, actor, "setup.reopen")
