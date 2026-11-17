"""Service health: the components and the rules that judge them.

Shared by ``GET /v1/health`` / ``/v1/health/ready`` (``app.api.v1.health``,
which shapes the answer per caller) and by the Kurier watchdog ping
(``app.core.kurier_watchdog``), which reports the same verdict to Kurier —
one definition of "healthy" (ADR-0003).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..config import get_settings
from ..db.session import healthcheck as db_healthcheck
from ..utils.time import utc_now

logger = logging.getLogger(__name__)

# A delivery still pending this long past its scheduled next attempt means the
# retry worker is not draining the outbox (audit F32).
OUTBOX_OVERDUE_SEC = 120

# Components whose failure means the service is not doing its job — a "down"
# here fails readiness (503), not just the informational /health body.
ESSENTIAL = frozenset({"database", "engine", "delivery"})


class ComponentHealth(BaseModel):
    """Per-component health snapshot."""

    status: Literal["ok", "degraded", "down", "unknown"]
    detail: str | None = None
    # Stable machine form of ``detail`` for clients that translate it (the
    # admin UI): ``code`` names the message, ``params`` fills it. ``detail``
    # stays the English rendering for logs and scripts.
    code: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


def overall(components: dict[str, ComponentHealth]) -> Literal["ok", "degraded", "down"]:
    statuses = [c.status for c in components.values()]
    if any(s == "down" for s in statuses):
        return "down"
    if any(s == "degraded" for s in statuses):
        return "degraded"
    return "ok"


def essential_down(components: dict[str, ComponentHealth]) -> list[str]:
    """Essential components currently reporting 'down' (drives readiness)."""
    return [n for n, c in components.items() if n in ESSENTIAL and c.status == "down"]


def task_component(alive: bool, name: str) -> ComponentHealth:
    return ComponentHealth(
        status="ok" if alive else "down",
        detail="running" if alive else f"{name} task not running",
        code="task_running" if alive else "task_stopped",
    )


def engine_component() -> ComponentHealth:
    """Down when the task is gone, or alive but stuck: its loop has not come
    round for ``RuleEngine.STALL_SEC`` (IP-01) — no rule is being evaluated."""
    from .engine import RuleEngine, get_engine

    engine = get_engine()
    if not engine.is_alive():
        return task_component(False, "rule engine")
    stalled = engine.stalled_for()
    if stalled > RuleEngine.STALL_SEC:
        return ComponentHealth(status="down", detail=f"rule engine stuck for {int(stalled)}s",
                               code="engine_stalled", params={"seconds": int(stalled)})
    return task_component(True, "rule engine")


async def background_components() -> dict[str, ComponentHealth]:
    """Liveness of the essential background tasks + outbox backlog (F32)."""
    from .delivery_worker import get_delivery_worker
    from .schedule_service import get_schedule_service

    comps: dict[str, ComponentHealth] = {
        "engine": engine_component(),
        "scheduler": task_component(get_schedule_service().is_alive(), "scheduler"),
        "delivery": task_component(get_delivery_worker().is_alive(), "delivery worker"),
    }
    comps["outbox"] = await outbox_backlog()
    return comps


async def outbox_backlog() -> ComponentHealth:
    """Degraded when pending deliveries are overdue — the worker is alive but
    not draining, or was down long enough to pile up a backlog (F32)."""
    try:
        from sqlalchemy import func, select

        from ..db.models import Delivery, DeliveryState
        from ..db.session import get_session_factory

        cutoff = utc_now() - timedelta(seconds=OUTBOX_OVERDUE_SEC)
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
                detail=f"{overdue} delivery(ies) overdue >{OUTBOX_OVERDUE_SEC}s",
                code="outbox_overdue", params={"count": overdue, "seconds": OUTBOX_OVERDUE_SEC},
            )
        return ComponentHealth(status="ok", detail="no overdue deliveries", code="outbox_clear")
    except Exception as e:  # pragma: no cover — never let the probe crash health
        logger.debug("outbox backlog probe failed: %s", e)
        return ComponentHealth(status="unknown", detail="backlog probe unavailable", code="outbox_probe_unavailable")


async def collect_components() -> dict[str, ComponentHealth]:
    settings = get_settings()

    db_ok, db_err = await db_healthcheck()
    db_status: Literal["ok", "degraded", "down", "unknown"] = "ok" if db_ok else "down"

    components = {
        "service": ComponentHealth(status="ok", detail=f"tz={settings.tz}", code="timezone", params={"tz": settings.tz}),
        "database": ComponentHealth(
            status=db_status, detail=db_err or "SELECT 1 OK",
            code="db_error" if db_err else "db_ok", params={"error": db_err} if db_err else {},
        ),
        "mqtt": await mqtt_component(),
    }
    components.update(await background_components())
    return components


async def mqtt_component() -> ComponentHealth:
    from .manager import get_manager

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
