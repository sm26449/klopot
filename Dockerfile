# syntax=docker/dockerfile:1.7
# alertd — multi-stage build
#
# Stage 1: install dependencies into a virtual env using uv (fast).
# Stage 2: minimal runtime, non-root user, copy only what we need.

ARG PYTHON_VERSION=3.12-slim-bookworm

# ───────────────────────── Stage 1: builder ─────────────────────────
FROM python:${PYTHON_VERSION} AS builder

# uv: fast Python package installer (drop-in pip replacement). Installed
# from PyPI rather than COPY --from=ghcr.io/astral-sh/uv — a stale GHCR
# login on the build host made that pull fail with "denied" (2026-09-09)
# and the image could not be rebuilt locally at all.
RUN pip install --no-cache-dir uv==0.5.4

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install deps first (cached layer) — pyproject.toml only
COPY pyproject.toml ./
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv pip install --no-cache -e .

# ───────────────────────── Stage 2: runtime ─────────────────────────
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# Non-root user
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --shell /bin/bash app

# Copy the virtual environment from builder
COPY --from=builder --chown=app:app /opt/venv /opt/venv

WORKDIR /app

# Copy app source (after venv so that source changes don't bust the deps layer)
COPY --chown=app:app app/ ./app/
COPY --chown=app:app scripts/ ./scripts/
COPY --chown=app:app alembic/ ./alembic/
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app pyproject.toml ./

USER app

EXPOSE 5090

# Healthcheck — Docker probes the readiness endpoint, which returns 503 when
# an essential component (DB, rule engine, delivery worker) is down, instead
# of /v1/health which always returns 200 with the status only in the body (F32).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5090/v1/health/ready', timeout=3).status==200 else 1)"

# Production server: gunicorn with a SINGLE uvicorn worker.
# alertd is single-process by design (audit R12): each process owns the rule
# engine, input adapters, state cache and delivery worker, with no shared
# leadership / cache invalidation / delivery claims across processes. Do NOT
# raise --workers or run multiple replicas — that would double-fire rules and
# double-send notifications. See docs/DEPLOY.md.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "app.worker.KlopotWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:5090", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
