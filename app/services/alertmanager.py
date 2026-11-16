"""Ingest an Alertmanager / Grafana alert group into external episodes.

Each new fingerprint opens an episode and sends its notice, so what one
request may open is budgeted per input (inputs/alertmanager.py ``LIMITS``):
at most ``max_new_episodes_per_min`` new episodes a minute (GCRA, the same
limiter as API keys) and ``max_active_episodes`` open at once. A firing
alert past either is not opened — counted as ``over_budget`` and reported in
one notice per request; Alertmanager sends it again while it keeps firing,
so it opens once there is room. Repeats and resolutions are never budgeted:
they only touch episodes that already exist.

The active count is read once per request (one index range on
``active_source_key``), so two requests at the same moment may together
pass the cap by a few — a bound on runaway growth, not an exact quota.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import fire_service
from ..db.models import Incident, Input, Template
from ..inputs import alertmanager as am
from ..utils.rate_limit import PerMinuteLimiter

logger = logging.getLogger(__name__)

# New episodes each input may open, by input id.
_NEW_EPISODES = PerMinuteLimiter()


def reset_episode_budgets() -> None:
    """Forget every input's new-episode allowance (tests: ids repeat)."""
    _NEW_EPISODES.forget()


async def _active_episodes(session: AsyncSession, input_id: int, keys: list[str]) -> tuple[int, set[str]]:
    """How many episodes of the input are open, and which of ``keys`` are."""
    prefix = am.episode_prefix(input_id)
    count = (await session.execute(
        select(func.count()).select_from(Incident).where(Incident.active_source_key.like(prefix + "%"))
    )).scalar_one()
    open_keys = set((await session.execute(
        select(Incident.active_source_key).where(Incident.active_source_key.in_(keys))
    )).scalars()) if keys else set()
    return count, {k for k in open_keys if k}


async def ingest(session: AsyncSession, input_row: Input, payload: Any) -> dict[str, Any]:
    """Process one webhook body. The caller commits. Returns a summary:
    ``{alerts, opened, repeat, resolved, ignored, over_budget, truncated, errors}``."""
    config = dict(input_row.config or {})
    group = am.parse_group(payload, max_alerts=am.limit(config, "max_alerts"))
    templates = {t for (t,) in (await session.execute(select(Template.type))).all()}
    counts: Counter[str] = Counter()
    source = f"alertmanager:{input_row.name}"

    firing = [(alert, am.episode_key(input_row.id, alert)) for alert in group.alerts if alert.status == "firing"]
    active, open_keys = await _active_episodes(session, input_row.id, [key for _, key in firing])
    max_active = am.limit(config, "max_active_episodes")
    per_min = am.limit(config, "max_new_episodes_per_min")

    for alert in group.alerts:
        key = am.episode_key(input_row.id, alert)
        ctx = am.alert_context(alert, group.common)
        if alert.status != "firing":
            outcome = await fire_service.resolve_episode(
                session, source_key=key, context=ctx, started_at=alert.starts_at,
            )
            counts[outcome.episode] += 1
            continue
        if key not in open_keys:
            # Would open a new episode: within both budgets, or not at all.
            if active >= max_active or not _NEW_EPISODES.admit(input_row.id, per_min).allowed:
                counts["over_budget"] += 1
                continue
        outcome = await fire_service.fire_episode(
            session, source_kind="alertmanager", source_key=key, name=am.episode_name(alert),
            type=am.choose_type(alert, config, templates), context=ctx, source=source,
            started_at=alert.starts_at, resolved_type=config.get("resolved_type") or None,
        )
        if outcome.episode == "opened" and key not in open_keys:
            active += 1
            open_keys.add(key)
        counts[outcome.episode] += 1

    if group.truncated or counts["over_budget"]:
        logger.warning("alertmanager input %s: %d alert(s) truncated, %d over budget",
                       input_row.name, group.truncated, counts["over_budget"])
        await fire_service.fire(
            session, type=am.TRUNCATED_TYPE, source=source,
            context={"input": input_row.name, "truncated": group.truncated, "over_budget": counts["over_budget"],
                     **{f"am.{k}": v for k, v in group.common.items()}},
        )

    return {
        "alerts": len(group.alerts),
        "opened": counts["opened"], "repeat": counts["repeat"], "resolved": counts["resolved"],
        "ignored": counts["stale"] + counts["not_found"], "over_budget": counts["over_budget"],
        "truncated": group.truncated, "errors": group.errors,
    }
