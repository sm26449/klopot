"""Ingest an Alertmanager / Grafana alert group into external episodes."""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import fire_service
from ..db.models import Input, Template
from ..inputs import alertmanager as am

logger = logging.getLogger(__name__)


async def ingest(session: AsyncSession, input_row: Input, payload: Any) -> dict[str, Any]:
    """Process one webhook body. The caller commits. Returns a summary:
    ``{alerts, opened, repeat, resolved, ignored, truncated, errors}``."""
    config = dict(input_row.config or {})
    group = am.parse_group(payload, max_alerts=int(config.get("max_alerts") or am.DEFAULT_MAX_ALERTS))
    templates = {t for (t,) in (await session.execute(select(Template.type))).all()}
    counts: Counter[str] = Counter()
    source = f"alertmanager:{input_row.name}"

    for alert in group.alerts:
        key = am.episode_key(input_row.id, alert)
        ctx = am.alert_context(alert, group.common)
        if alert.status == "firing":
            outcome = await fire_service.fire_episode(
                session, source_kind="alertmanager", source_key=key, name=am.episode_name(alert),
                type=am.choose_type(alert, config, templates), context=ctx, source=source,
                started_at=alert.starts_at, resolved_type=config.get("resolved_type") or None,
            )
        else:
            outcome = await fire_service.resolve_episode(
                session, source_key=key, context=ctx, started_at=alert.starts_at,
            )
        counts[outcome.episode] += 1

    if group.truncated:
        logger.warning("alertmanager input %s: %d alert(s) truncated", input_row.name, group.truncated)
        await fire_service.fire(
            session, type=am.TRUNCATED_TYPE, source=source,
            context={"input": input_row.name, "truncated": group.truncated, **{f"am.{k}": v for k, v in group.common.items()}},
        )

    return {
        "alerts": len(group.alerts),
        "opened": counts["opened"], "repeat": counts["repeat"], "resolved": counts["resolved"],
        "ignored": counts["stale"] + counts["not_found"],
        "truncated": group.truncated, "errors": group.errors,
    }
