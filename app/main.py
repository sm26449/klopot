"""FastAPI app factory + lifespan.

S2 wiring:
- Initialize SQLAlchemy async engine on startup
- Auto-apply Alembic migrations (configurable via env)
- Run seed script (idempotent: bootstrap admin key, default channels, settings)
- Graceful shutdown disposes the engine
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from alembic import command
from alembic.config import Config as AlembicConfig

from . import __version__
from .api.v1 import router as v1_router
from .config import get_settings
from .db import dispose_engine, init_engine

logger = logging.getLogger(__name__)


def _run_migrations_sync() -> None:
    """Apply Alembic migrations up to head.

    Runs synchronously — alembic.env uses ``asyncio.run`` internally,
    which can't be called from inside our running event loop, so the
    caller (lifespan) wraps this in ``asyncio.to_thread``.
    """
    cfg = AlembicConfig("alembic.ini")
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup → Shutdown sequence.

    Order on startup:
      1. Apply Alembic migrations (creates schema if missing,
         updates to head) — fail-fast on error
      2. Init DB engine + session factory
      3. Run seed script (default channels, settings, bootstrap key)
      4. Input manager (MQTT + adapters)
      5. Rule engine ticker
      6. Schedule service
      7. Retention sweep
      8. Channel breaker publisher
    Reverse on shutdown.
    """
    settings = get_settings()
    logger.info(
        "alertd starting", extra={"version": __version__, "tz": settings.tz}
    )

    # 1. Migrations — wrapped in to_thread because alembic env.py uses
    #    asyncio.run() which can't nest inside our running event loop.
    #    Fail-fast: a container in a visible restart loop beats a
    #    silently-running service on a half-migrated schema.
    try:
        await asyncio.to_thread(_run_migrations_sync)
    except Exception:
        logger.exception("Alembic upgrade failed — aborting startup (fail-fast)")
        raise

    # 2. Engine
    init_engine()

    # 3. Seed
    try:
        from scripts.seed import run_seed

        seeded = await run_seed()
        if any(v > 0 for v in seeded.values()):
            logger.info("Seed counts: %s", seeded)
    except Exception:
        logger.exception("Seed step failed; check DB state manually")

    # 4. Input manager — connects MQTT, builds resolver, starts adapters
    try:
        from .core.manager import get_manager

        await get_manager().start()
    except Exception:
        logger.exception("Input manager failed to start; service runs but no inputs")

    # 5. Rule engine — async ticker that evaluates rules against state cache
    try:
        from .core.engine import get_engine

        await get_engine().start()
    except Exception:
        logger.exception("Rule engine failed to start; service runs but no rule eval")

    # 6. Schedule service — fires schedules on cron
    try:
        from .core.schedule_service import get_schedule_service

        await get_schedule_service().start()
    except Exception:
        logger.exception("Schedule service failed to start; service runs but no scheduled fires")

    # 6b. Delivery worker — retries the transactional outbox (audit A01)
    try:
        from .core.delivery_worker import get_delivery_worker

        await get_delivery_worker().start()
    except Exception:
        logger.exception("Delivery worker failed to start; failed deliveries won't retry")

    # 7. Retention sweep — hourly background task pruning old log + audit rows
    try:
        from .core.retention import get_retention_service

        await get_retention_service().start()
    except Exception:
        logger.exception("Retention service failed to start; logs will grow unbounded")

    # 7b. Escalation — re-page unacked criticals once after N minutes
    try:
        from .core.escalation import get_escalation_service

        await get_escalation_service().start()
    except Exception:
        logger.exception("Escalation service failed to start; unacked criticals won't re-page")

    # 7c. Daily suppressed-alerts digest
    try:
        from .core.digest import get_digest_service

        await get_digest_service().start()
    except Exception:
        logger.exception("Digest service failed to start")

    # 8. Channel-breaker state publisher — every 30s snapshots
    #    CircuitBreaker._state into the state cache so the rule
    #    engine can fire on stuck-open channels (audit M-8).
    try:
        from .channels.manager import get_channel_manager

        await get_channel_manager().start_breaker_publisher()
    except Exception:
        logger.exception("Channel breaker publisher failed to start")

    yield

    try:
        from .channels.manager import get_channel_manager

        await get_channel_manager().stop_breaker_publisher()
    except Exception:
        logger.exception("Channel breaker publisher shutdown failed")
    try:
        from .core.digest import get_digest_service

        await get_digest_service().stop()
    except Exception:
        logger.exception("Digest service shutdown failed")
    try:
        from .core.escalation import get_escalation_service

        await get_escalation_service().stop()
    except Exception:
        logger.exception("Escalation service shutdown failed")
    try:
        from .core.retention import get_retention_service

        await get_retention_service().stop()
    except Exception:
        logger.exception("Retention service shutdown failed")
    try:
        from .core.schedule_service import get_schedule_service

        await get_schedule_service().stop()
    except Exception:
        logger.exception("schedule service stop failed")
    try:
        from .core.delivery_worker import get_delivery_worker

        await get_delivery_worker().stop()
    except Exception:
        logger.exception("Delivery worker shutdown failed")
    try:
        from .core.engine import get_engine

        await get_engine().stop()
    except Exception:
        logger.exception("Rule engine shutdown failed")
    try:
        from .core.manager import get_manager

        await get_manager().stop()
    except Exception:
        logger.exception("Input manager shutdown failed")
    await dispose_engine()
    logger.info("alertd shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    # Logging — JSON or console depending on ALERTD_LOG_FORMAT.
    # Replaces the prior basicConfig call; configure_logging() also
    # wires the trace_id contextvar formatter.
    from .logging_setup import configure_logging, request_trace_middleware

    configure_logging()

    # Interactive docs leak the full API shape; disable them (and the OpenAPI
    # schema they need) on a prod/TLS deploy unless explicitly enabled (S-12).
    _docs_on = get_settings().docs_enabled_effective
    app = FastAPI(
        title="alertd",
        description=(
            "Notification microservice — declarative inputs, rules, "
            "templates, channels. See /docs for the full API surface."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if _docs_on else None,
        redoc_url="/redoc" if _docs_on else None,
        openapi_url="/openapi.json" if _docs_on else None,
    )

    # Request-body byte cap (audit A-08). Registered first so it sits just
    # INSIDE the trace / security-header wrappers: it refuses an oversized body
    # with 413 before any route handler buffers or parses it (no other
    # middleware reads the body), and the 413 still carries the standard
    # response headers on the way out.
    from .body_limit import BodySizeLimitMiddleware

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)

    # Trace-id middleware — every request gets a UUID4 (or honors an
    # incoming X-Trace-Id header); the id appears in every log line
    # for correlation across services.
    app.middleware("http")(request_trace_middleware)

    # CORS — only installed when ALERTD_CORS_ORIGINS is non-empty.
    # Default deployment is proxy-only (no CORS), so don't add the
    # middleware unless explicitly opted in.
    if settings.cors_origin_list:
        from fastapi.middleware.cors import CORSMiddleware

        # PUT is required for routing replacement (PUT /v1/templates/{type}
        # /channels); without it a cross-origin API-key client failed
        # preflight (audit F40). This CORS surface is for machine (API-key)
        # cross-origin clients — browser session/CSRF administration stays
        # same-origin and is NOT enabled by allow_credentials alone.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["X-API-Key", "Content-Type", "X-Input-Token"],
        )

    # Log unhandled exceptions with full traceback, then return 500.
    # Replaces FastAPI's silent "Internal Server Error" body so operators
    # see what crashed.
    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):
        # Audit A20: never return str(exc) — it leaks SQL text, bound
        # parameters and internal detail to the client. Log the full
        # traceback (redacted-safe server side) under a short trace id,
        # and hand the client only that id to quote in a report.
        import uuid

        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
        logger.exception(
            "Unhandled exception [trace=%s] on %s %s",
            trace_id, request.method, request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "trace_id": trace_id,
                }
            },
            headers={"X-Trace-Id": trace_id},
        )

    # Baseline hardening headers on every API response. The admin SPA
    # adds its own strict CSP in app/admin_ui (Swagger UI at /docs
    # loads from a CDN, so no CSP here).
    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    app.include_router(v1_router, prefix="/v1")

    # Admin UI (static SPA) — ALERTD_ADMIN_UI_ENABLED
    from .admin_ui import mount_admin_ui

    if mount_admin_ui(app):
        logger.info("admin UI mounted at /admin")

    return app


# Module-level singleton (gunicorn / uvicorn entry point).
app = create_app()
