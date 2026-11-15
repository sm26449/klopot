"""Health and version endpoints."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from ... import __version__
from ...config import get_settings
from ...db.session import healthcheck as db_healthcheck
from ...utils.time import utc_now

logger = logging.getLogger(__name__)
router = APIRouter()

# A delivery still pending this long past its scheduled next attempt means the
# retry worker is not draining the outbox (audit F32).
_OUTBOX_OVERDUE_SEC = 120

# Components whose failure means the service is not doing its job — a "down"
# here fails readiness (503), not just the informational /health body.
_ESSENTIAL = frozenset({"database", "engine", "delivery"})


class ComponentHealth(BaseModel):
    """Per-component health snapshot."""

    status: Literal["ok", "degraded", "down", "unknown"]
    detail: str | None = None
    # Stable machine form of ``detail`` for clients that translate it (the
    # admin UI): ``code`` names the message, ``params`` fills it. ``detail``
    # stays the English rendering for logs and scripts.
    code: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """``GET /v1/health`` response.

    HTTP status is always 200 — clients inspect ``status`` field.
    Degraded components don't trigger Kubernetes restart loops.
    """

    status: Literal["ok", "degraded", "down"]
    service: str = Field(default="alertd")
    version: str = Field(default=__version__)
    components: dict[str, ComponentHealth]
    # Whether the interactive API docs are served (audit S-12); the admin UI
    # hides its /docs links when they are off, so they don't 404 in prod.
    docs_enabled: bool = Field(default=True)


def _overall(components: dict[str, ComponentHealth]) -> Literal["ok", "degraded", "down"]:
    statuses = [c.status for c in components.values()]
    if any(s == "down" for s in statuses):
        return "down"
    if any(s == "degraded" for s in statuses):
        return "degraded"
    return "ok"


def _essential_down(components: dict[str, ComponentHealth]) -> list[str]:
    """Essential components currently reporting 'down' (drives readiness)."""
    return [n for n, c in components.items() if n in _ESSENTIAL and c.status == "down"]


def _task_component(alive: bool, name: str) -> ComponentHealth:
    return ComponentHealth(
        status="ok" if alive else "down",
        detail="running" if alive else f"{name} task not running",
        code="task_running" if alive else "task_stopped",
    )


async def _background_components() -> dict[str, ComponentHealth]:
    """Liveness of the essential background tasks + outbox backlog (F32)."""
    from ...core.delivery_worker import get_delivery_worker
    from ...core.engine import get_engine
    from ...core.schedule_service import get_schedule_service

    comps: dict[str, ComponentHealth] = {
        "engine": _task_component(get_engine().is_alive(), "rule engine"),
        "scheduler": _task_component(get_schedule_service().is_alive(), "scheduler"),
        "delivery": _task_component(get_delivery_worker().is_alive(), "delivery worker"),
    }
    comps["outbox"] = await _outbox_backlog()
    return comps


async def _outbox_backlog() -> ComponentHealth:
    """Degraded when pending deliveries are overdue — the worker is alive but
    not draining, or was down long enough to pile up a backlog (F32)."""
    try:
        from sqlalchemy import func, select

        from ...db.models import Delivery, DeliveryState
        from ...db.session import get_session_factory

        cutoff = utc_now() - timedelta(seconds=_OUTBOX_OVERDUE_SEC)
        factory = get_session_factory()
        async with factory() as session:
            overdue = (
                await session.execute(
                    select(func.count())
                    .select_from(Delivery)
                    .where(Delivery.state == DeliveryState.pending)
                    .where(Delivery.next_attempt_at.is_not(None))
                    .where(Delivery.next_attempt_at < cutoff)
                )
            ).scalar_one()
        if overdue:
            return ComponentHealth(
                status="degraded",
                detail=f"{overdue} delivery(ies) overdue >{_OUTBOX_OVERDUE_SEC}s",
                code="outbox_overdue", params={"count": overdue, "seconds": _OUTBOX_OVERDUE_SEC},
            )
        return ComponentHealth(status="ok", detail="no overdue deliveries", code="outbox_clear")
    except Exception as e:  # pragma: no cover — never let the probe crash health
        logger.debug("outbox backlog probe failed: %s", e)
        return ComponentHealth(status="unknown", detail="backlog probe unavailable", code="outbox_probe_unavailable")


async def _collect_components() -> dict[str, ComponentHealth]:
    settings = get_settings()

    db_ok, db_err = await db_healthcheck()
    db_status: Literal["ok", "degraded", "down", "unknown"] = "ok" if db_ok else "down"

    components = {
        "service": ComponentHealth(status="ok", detail=f"tz={settings.tz}", code="timezone", params={"tz": settings.tz}),
        "database": ComponentHealth(
            status=db_status, detail=db_err or "SELECT 1 OK",
            code="db_error" if db_err else "db_ok", params={"error": db_err} if db_err else {},
        ),
        "mqtt": await _mqtt_component(),
    }
    components.update(await _background_components())
    return components


async def _mqtt_component() -> ComponentHealth:
    from ...core.manager import get_manager

    adapters = get_manager().adapter_health()
    critical = {n: h for n, h in adapters.items() if h.get("critical")}
    optional = {n: h for n, h in adapters.items() if not h.get("critical")}
    opt_down = [n for n, h in optional.items() if not h.get("connected")]
    opt_note = f" · optional down (ignored): {opt_down}" if opt_down else ""
    # Shared by every code below; ``optional_down`` lets a client add the note.
    base: dict[str, Any] = {"optional_down": opt_down} if opt_down else {}

    if not adapters:
        return ComponentHealth(status="unknown", detail="no inputs declared", code="inputs_none")
    if not critical:
        return ComponentHealth(
            status="ok", detail=f"no critical inputs; {len(adapters)} optional{opt_note}",
            code="inputs_optional_only", params={**base, "total": len(adapters)},
        )
    connected = [n for n, h in critical.items() if h.get("connected")]
    counts = {**base, "connected": len(connected), "total": len(critical)}
    if len(connected) == len(critical):
        return ComponentHealth(
            status="ok", detail=f"critical: {len(connected)}/{len(critical)} connected{opt_note}",
            code="inputs_connected", params=counts,
        )
    if connected:
        down = [n for n in critical if n not in connected]
        return ComponentHealth(
            status="degraded",
            detail=f"critical connected: {len(connected)}/{len(critical)} — down: {down}{opt_note}",
            code="inputs_partial", params={**counts, "down": down},
        )
    err = next((h.get("error") for h in critical.values() if h.get("error")), None)
    return ComponentHealth(
        status="down",
        detail=f"all critical inputs down{f' — last error: {err}' if err else ''}{opt_note}",
        code="inputs_down", params={**base, "error": err} if err else base,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description=(
        "Returns the overall service status plus a per-component health map. "
        "Always returns HTTP 200 — inspect the body to determine status. "
        "For a pass/fail probe that fails on essential-component outages, use "
        "``/v1/health/ready`` (returns 503 when not ready)."
    ),
)
async def health() -> HealthResponse:
    """Full health probe: DB, critical inputs, and the essential background
    tasks (rule engine, scheduler, delivery worker) plus outbox backlog.

    Always HTTP 200 — inspect the body. Only CRITICAL adapters drive the
    mqtt status; an optional input being down is surfaced but never fails
    health (a dead optional poller must not flip a downstream "pipeline
    DOWN" indicator). A dead essential background task reports 'down' here
    AND fails ``/v1/health/ready`` (F32).
    """
    components = await _collect_components()
    return HealthResponse(status=_overall(components), components=components, docs_enabled=get_settings().docs_enabled_effective)


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Readiness probe (fails on essential outages)",
    description=(
        "Returns HTTP 200 when every essential component (database, rule "
        "engine, delivery worker) is up, and HTTP 503 when one is down — so "
        "an orchestrator or the container healthcheck acts on a dead engine "
        "or retry worker instead of a body that always says 200 (F32)."
    ),
    responses={503: {"model": HealthResponse, "description": "Not ready"}},
)
async def readiness(response: Response) -> HealthResponse:
    components = await _collect_components()
    down = _essential_down(components)
    body = HealthResponse(status=_overall(components), components=components, docs_enabled=get_settings().docs_enabled_effective)
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
