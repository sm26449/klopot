"""``/v1/settings`` — effective runtime settings (read-only).

Audit finding H-6: the ``settings`` DB table exists but is NOT read by
the runtime — effective values come exclusively from the environment
(:mod:`app.config`). Exposing the DB row would mislead the operator
into thinking an edit takes effect. So this endpoint returns the
*effective* values (from ``get_settings()``), each tagged with its
source (``env`` when the variable was set, else ``default``) and marked
``read_only``. There is deliberately NO ``PATCH`` in v1 — changing
behaviour means changing the environment + restart.

Secrets are never included: ``database_url`` is masked and the MQTT /
bootstrap passwords are omitted entirely.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.engine import make_url

from ...auth import Actor, require_scope
from ...config import get_settings

router = APIRouter()

# Operationally-relevant, non-secret settings surfaced to the UI.
_EXPOSED: tuple[str, ...] = (
    "service_name",
    "version",
    "bind_host",
    "bind_port",
    "tz",
    "log_level",
    "log_format",
    "default_eval_interval_sec",
    "idempotency_window_sec",
    "log_retention_days",
    "audit_retention_days",
    "circuit_breaker_threshold",
    "circuit_breaker_open_sec",
    "eval_error_disable_threshold",
    "escalation_after_min",
    "escalation_channel",
    "digest_hour",
    "admin_ui_enabled",
    "session_idle_hours",
    "session_max_days",
    "cookie_secure",
    "login_max_failures",
    "login_max_failures_per_ip",
    "login_lockout_min",
    "auth_history_days",
    "trusted_proxy_cidrs",
)

def _mask_db_url(url: str) -> str:
    """Hide the password component of a SQLAlchemy URL.

    Uses SQLAlchemy's own URL parser rather than a regex: a password containing
    ``/`` (or other URL metacharacters) broke the regex, leaking the tail of the
    password to a read-scoped caller (audit S-03)."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "***"


@router.get(
    "/settings",
    summary="Effective runtime settings (read-only)",
    description=(
        "The values the service actually runs with, sourced from the "
        "environment. Each item is marked read_only=true and tagged with "
        "its source (env/default). No PATCH in v1 (see audit H-6)."
    ),
)
async def get_effective_settings(
    actor: Actor = Depends(require_scope("read")),
) -> dict[str, Any]:
    s = get_settings()
    set_fields = s.model_fields_set
    items: list[dict[str, Any]] = []
    for key in _EXPOSED:
        value = getattr(s, key, None)
        items.append({
            "key": key,
            "value": value,
            "source": "env" if key in set_fields else "default",
            "read_only": True,
        })
    # database_url is always shown masked, flagged as a secret-bearing field.
    items.append({
        "key": "database_url",
        "value": _mask_db_url(s.database_url),
        "source": "env" if "database_url" in set_fields else "default",
        "read_only": True,
    })
    return {"items": items}
