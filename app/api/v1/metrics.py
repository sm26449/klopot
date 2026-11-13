"""``GET /v1/metrics`` — Prometheus exposition.

Plain-text scrape endpoint, no auth (network-level ACL is the
expected control). Refreshes pull-state gauges (log table size,
input lag, breaker state) right before serving so values are fresh
on each scrape.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import _HEADER, get_current_actor
from ...config import get_settings
from ...db import get_session
from ...db.models import NotificationLog
from ...metrics import (
    AGGREGATE_OVERFLOW,
    INPUT_CONNECTED,
    INPUT_MSG_LAG_SEC,
    LOG_TABLE_ROWS,
    render_latest,
    set_breaker_state,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _metrics_guard(
    request: Request,
    api_key: str | None = Depends(_HEADER),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Require a read-scoped key for /v1/metrics when configured (audit S-12).

    Default-closed on a TLS/prod deploy (``metrics_require_auth_effective``);
    open on a local/dev deploy, where Prometheus scrapes it over the loopback."""
    if not get_settings().metrics_require_auth_effective:
        return
    actor = await get_current_actor(request, api_key, session)  # 401 if unauthenticated
    if not actor.has_scope("read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="metrics require a read-scoped key")


@router.get(
    "/metrics",
    summary="Prometheus exposition",
    description=(
        "Plain-text Prometheus metrics. Designed to be scraped from "
        "inside the docker network. Includes engine fires, dispatch "
        "latency, channel breaker state, input connectivity / lag, "
        "and the notifications_log table size."
    ),
    responses={200: {"content": {"text/plain": {}}}},
)
async def prometheus(
    session: AsyncSession = Depends(get_session),
    _guard: None = Depends(_metrics_guard),
) -> Response:
    # ── Pull-state gauges: refresh from runtime each scrape ──
    try:
        from ...channels.manager import get_channel_manager

        mgr = get_channel_manager()
        # Iterate PER-CHANNEL breaker health; health(None) returns loaded
        # adapter kinds, not channel health, so the old loop never exported
        # any real breaker state (audit F36).
        for name, h in mgr.breaker_states().items():
            set_breaker_state(name, (h or {}).get("state", "closed"))
    except Exception:
        logger.debug("breaker state refresh failed", exc_info=True)

    try:
        from ...core.manager import get_manager

        imgr = get_manager()
        for name, h in imgr.adapter_health().items():
            INPUT_CONNECTED.labels(input=name).set(1 if h.get("connected") else 0)
            last = h.get("last_msg_ts")
            lag = (time.time() - last) if last else 0.0
            INPUT_MSG_LAG_SEC.labels(input=name).set(max(0.0, lag))
        AGGREGATE_OVERFLOW.set(len(imgr.resolver.overflowed_aggregates()))
    except Exception:
        logger.debug("input lag refresh failed", exc_info=True)

    try:
        cnt = (
            await session.execute(select(func.count()).select_from(NotificationLog))
        ).scalar_one()
        LOG_TABLE_ROWS.set(cnt)
    except Exception:
        logger.debug("log table count refresh failed", exc_info=True)

    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)
