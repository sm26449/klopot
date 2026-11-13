"""``POST /v1/fire`` — external callers fire alerts.

The simple endpoint NR / scripts / 3rd-party apps use. Caller
provides ``type`` + ``context``; the service handles rendering,
gating, channel routing.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...core import dispatcher as dispatcher_module
from ...db import get_session
from ...schemas.fire import FireRequest, FireResponse

router = APIRouter()


@router.post(
    "/fire",
    response_model=FireResponse,
    status_code=202,
    summary="Fire a notification by type",
    description=(
        "External callers (Node-RED, scripts, third-party apps) post here "
        "with `type` and `context` (vars used by the template). The service "
        "handles routing, throttling, and channel dispatch. Caller does NOT "
        "need to know channels, credentials, or templates."
    ),
)
async def post_fire(
    body: FireRequest,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("fire")),
) -> FireResponse:
    envelope = dispatcher_module.FireEnvelope(
        type=body.type,
        context=body.context,
        test=body.test,
        source=body.source or actor.name,
        rule_id=None,  # external fires don't track a rule
    )
    result = await dispatcher_module.fire(envelope, session)
    await session.commit()
    return FireResponse(**result.as_dict())
