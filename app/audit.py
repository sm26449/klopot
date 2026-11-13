"""Audit log helper.

Each admin write should call ``await record(...)`` to leave a
trail in ``audit_log``. Calling code passes the actor + before/after
snapshots; this module handles serialization and persistence.

Usage::

    from .audit import record_change

    # In a CRUD handler:
    before = serialize(row)
    row.update(...)
    await record_change(session, actor, "template.update",
                       resource_kind="template",
                       resource_id=str(row.id),
                       before=before, after=serialize(row))

The session is the SAME one mutating the resource — audit row is
committed transactionally with the change.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Actor
from .db.models import ActorKind, AuditLog


def _safe_jsonable(obj: Any) -> Any:
    """Round-trip through JSON to ensure the object is fully
    serializable (converts datetime, enum, decimal, etc. to strings).

    Returns a plain dict/list/scalar of JSON-safe types — safe to
    write into a SQLAlchemy JSON column.
    """
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return str(obj)


async def record_change(
    session: AsyncSession,
    actor: Actor,
    action: str,
    *,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Insert an audit_log row. Caller commits.

    Audit #121 (2026-05-17, v1.3.4): ``ts`` is set explicitly to
    ``utc_now()`` so the value is naive-UTC at rest. Pre-v1.3.4
    we relied on the SQL ``func.current_timestamp()`` default which
    used ``@@time_zone=SYSTEM`` (local time). The new code path
    aligns with ``notifications_log.fired_at`` so both tables now
    store UTC consistently. Migration 0004 normalises historical
    rows from local to UTC.
    """
    from .utils.time import utc_now
    if trace_id is None:
        # Correlate the audit row with the request's log trace by default
        # (audit A35): the middleware sets this contextvar per request.
        from .logging_setup import trace_id_var
        trace_id = trace_id_var.get()
    entry = AuditLog(
        ts=utc_now(),
        actor_kind=ActorKind(actor.kind),
        actor_id=actor.id,
        actor_name=actor.name,
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        before=_safe_jsonable(before) if before is not None else None,
        after=_safe_jsonable(after) if after is not None else None,
        trace_id=trace_id,
    )
    session.add(entry)


def model_to_dict(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    """Snapshot an ORM row to a JSON-friendly dict for before/after.

    Excludes private attrs and the SA state. ``exclude`` masks
    sensitive columns (``key_hash`` etc.) so they never reach the
    audit log.
    """
    excl = exclude or set()
    excl = excl | {"key_hash"}  # always mask
    out: dict[str, Any] = {}
    for k, v in obj.__dict__.items():
        if k.startswith("_"):
            continue
        if k in excl:
            out[k] = "<redacted>"
            continue
        out[k] = v
    # Channel / Input rows carry adapter config that may hold literal
    # secrets (audit 2026-11-07 C-2). Mask them through the central
    # registry so plaintext never lands in audit_log.before/after.
    resource = _SECRET_RESOURCE_BY_MODEL.get(type(obj).__name__)
    if resource and isinstance(out.get("config"), dict):
        from .secrets_registry import mask_config

        out["config"] = mask_config(resource, out.get("kind"), out["config"])
    return _safe_jsonable(out)


_SECRET_RESOURCE_BY_MODEL: dict[str, str] = {"Channel": "channel", "Input": "input"}
