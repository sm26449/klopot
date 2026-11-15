"""``POST /v1/fire`` — external callers fire alerts.

The simple endpoint NR / scripts / 3rd-party apps use. Caller
provides ``type`` + ``context``; the service handles rendering,
gating, channel routing.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...core import fire_service
from ...db import get_session
from ...schemas.fire import FireRequest, FireResponse
from ...utils.keys import bounded_key

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
        "need to know channels, credentials, or templates.\n\n"
        "With `idempotency_key` the fire belongs to an **episode**: the first "
        "`status: firing` opens it (an incident) and notifies, repeats while it "
        "is open notify nothing, `status: resolved` closes it and sends "
        "`resolved_type` if one was given. `episode` in the response says what "
        "happened. `test: true` ignores the key."
    ),
)
async def post_fire(
    body: FireRequest,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("fire")),
) -> FireResponse:
    source = body.source or actor.name
    if body.idempotency_key is None or body.test:
        if body.status == "resolved":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="status=resolved needs the idempotency_key of the episode to close",
            )
        result = await fire_service.fire(
            session, type=body.type, context=body.context, source=source, test=body.test,
        )
        await session.commit()
        return FireResponse(**result.as_dict())

    # Scope the key to the caller so two clients can't close each other's episodes.
    # The longest valid pair (64-character key name, 128-character idempotency
    # key) is 198 characters; the column holds 191.
    source_key = bounded_key(f"fire:{actor.name}:{body.idempotency_key}")
    if body.status == "firing":
        outcome = await fire_service.fire_episode(
            session, source_kind="fire", source_key=source_key, name=body.idempotency_key,
            type=body.type, context=body.context, source=source, resolved_type=body.resolved_type,
        )
    else:
        outcome = await fire_service.resolve_episode(session, source_key=source_key, context=body.context)
    await session.commit()
    return episode_response(outcome)


def episode_response(outcome: fire_service.EpisodeOutcome) -> FireResponse:
    if outcome.result is not None:
        response = FireResponse(**outcome.result.as_dict())
    else:
        response = FireResponse(
            id=outcome.incident_id or "", dispatched=False, channels=[], status=outcome.episode,
            title="", message="", severity="info",
        )
    response.incident_id = outcome.incident_id
    response.episode = outcome.episode
    return response
