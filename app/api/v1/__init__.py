"""API v1 router aggregation.

Each resource has its own module. They register an ``APIRouter``
which we include here. The parent router is mounted at ``/v1`` in
``app.main``.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    api_keys,
    audit,
    auth,
    channels,
    config,
    fire,
    health,
    inputs,
    log,
    meta,
    metrics,
    rules,
    schedules,
    settings,
    snooze,
    state,
    templates,
    variables,
)

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(metrics.router, tags=["metrics"])
router.include_router(state.router, tags=["state"])
router.include_router(fire.router, tags=["fire"])
router.include_router(log.router, tags=["log"])
router.include_router(audit.router, tags=["audit"])
router.include_router(config.router, tags=["config"])
router.include_router(settings.router, tags=["settings"])
router.include_router(meta.router, tags=["meta"])
router.include_router(templates.router, prefix="/templates", tags=["templates"])
router.include_router(rules.router, prefix="/rules", tags=["rules"])
router.include_router(channels.router, prefix="/channels", tags=["channels"])
router.include_router(api_keys.router, prefix="/api_keys", tags=["api_keys"])
router.include_router(inputs.router, prefix="/inputs", tags=["inputs"])
router.include_router(variables.router, prefix="/variables", tags=["variables"])
router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
router.include_router(snooze.router, prefix="/snooze", tags=["snooze"])

# All planned API modules are now live (F3: settings exposes effective
# env-sourced config read-only; meta serves UI form schemas).
