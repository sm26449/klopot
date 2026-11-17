"""Health and version endpoints."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from ... import __version__
from ...auth import Actor, get_optional_actor
from ...config import get_settings
from ...core.health import ComponentHealth
from ...core.health import collect_components as _collect_components
from ...core.health import engine_component as _engine_component  # noqa: F401 — tests
from ...core.health import essential_down as _essential_down
from ...core.health import overall as _overall

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthStatus(BaseModel):
    """``GET /v1/health`` for a caller without ``read``: the overall status
    only. The components name hosts, inputs and error texts, and the version
    tells an attacker what to try (public-exposure review F7, F13)."""

    status: Literal["ok", "degraded", "down"]
    service: str = Field(default="alertd")


class HealthResponse(HealthStatus):
    """``GET /v1/health`` for a ``read`` caller (an API key with ``read``, or
    a signed-in user): the status plus the component map.

    HTTP status is always 200 — clients inspect ``status`` field.
    Degraded components don't trigger Kubernetes restart loops.
    """

    version: str = Field(default=__version__)
    components: dict[str, ComponentHealth]
    # Whether the interactive API docs are served (audit S-12); the admin UI
    # hides its /docs links when they are off, so they don't 404 in prod.
    docs_enabled: bool = Field(default=True)


@router.get(
    "/health",
    response_model=HealthResponse | HealthStatus,
    summary="Service health check",
    description=(
        "Returns the overall service status; a caller with `read` (API key or "
        "signed-in user) also gets the version and the per-component map. "
        "Always returns HTTP 200 — inspect the body to determine status. "
        "For a pass/fail probe that fails on essential-component outages, use "
        "``/v1/health/ready`` (returns 503 when not ready)."
    ),
)
async def health(actor: Actor | None = Depends(get_optional_actor)) -> HealthResponse | HealthStatus:
    """Full health probe: DB, critical inputs, and the essential background
    tasks (rule engine, scheduler, delivery worker) plus outbox backlog.

    Always HTTP 200 — inspect the body. Only CRITICAL adapters drive the
    mqtt status; an optional input being down is surfaced but never fails
    health (a dead optional poller must not flip a downstream "pipeline
    DOWN" indicator). A dead essential background task reports 'down' here
    AND fails ``/v1/health/ready`` (F32).
    """
    return _shaped(await _collect_components(), actor)


def _shaped(components: dict[str, ComponentHealth], actor: Actor | None) -> HealthResponse | HealthStatus:
    """The body for this caller: everything for ``read``, the status alone
    otherwise."""
    if actor is not None and actor.has_scope("read"):
        return HealthResponse(status=_overall(components), components=components,
                              docs_enabled=get_settings().docs_enabled_effective)
    return HealthStatus(status=_overall(components))


@router.get(
    "/health/ready",
    response_model=HealthResponse | HealthStatus,
    summary="Readiness probe (fails on essential outages)",
    description=(
        "Returns HTTP 200 when every essential component (database, rule "
        "engine, delivery worker) is up, and HTTP 503 when one is down — so "
        "an orchestrator or the container healthcheck acts on a dead engine "
        "or retry worker instead of a body that always says 200 (F32). The "
        "body is shaped like `/v1/health`'s for the same caller."
    ),
    responses={503: {"model": HealthResponse | HealthStatus, "description": "Not ready"}},
)
async def readiness(response: Response,
                    actor: Actor | None = Depends(get_optional_actor)) -> HealthResponse | HealthStatus:
    components = await _collect_components()
    down = _essential_down(components)
    body = _shaped(components, actor)
    if down:
        response.status_code = 503
        logger.warning("Readiness FAIL — essential components down: %s", down)
    return body


# ── Version endpoint ──────────────────────────────────────────────


class VersionResponse(BaseModel):
    """``GET /v1/version`` body — lightweight identification.

    Separate from ``/health`` (which probes DB + MQTT) so caller-side
    deploy scripts can poll cheaply without touching infra deps."""

    service: str = Field(default="alertd")
    version: str = Field(default=__version__)


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Service version",
    description=(
        "Returns the running service version. Health-free and infra-free — "
        "use for deploy verification and client compatibility checks."
    ),
)
async def version() -> VersionResponse:
    return VersionResponse()
