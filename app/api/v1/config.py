"""``/v1/config`` — full config export / import / validate.

Useful for:
- Disaster recovery (export periodically, restore from YAML)
- Sharing rule sets between deployments
- Bulk apply via CLI
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import yaml
from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...config import get_settings
from ...core.engine import get_engine
from ...core.manager import get_manager
from ...db import get_session
from ...services import config_io
from ...utils.safe_yaml import BoundedYAMLError, load_bounded

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/config/export",
    summary="Export full configuration as YAML",
    description=(
        "Returns every config table (inputs, variables, templates, "
        "channels, routes, rules, schedules, settings) as a portable "
        "YAML document. Identifiers across sections use NAMES, not "
        "auto-generated ids — safe to apply on a different deployment.\n\n"
        "Set `?mask_secrets=true` to rewrite literal-looking secrets "
        "(bot_token, password, api_key fields) as `env:UNKNOWN_*` "
        "placeholders so the YAML is shareable."
    ),
)
async def export_config(
    mask_secrets: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> Response:
    data = await config_io.export_config(session, mask_secrets=mask_secrets)
    body = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True,
    )
    headers = {
        "Content-Disposition": 'attachment; filename="alertd-config.yaml"'
    }
    return Response(content=body, media_type="application/yaml", headers=headers)


@router.post(
    "/config/validate",
    summary="Validate a YAML config without writing",
    description=(
        "POST a YAML body — content-type `application/yaml` or "
        "`text/yaml`. Returns a plan: what would be created vs "
        "updated, plus any errors / warnings. Errors prevent import; "
        "warnings don't."
    ),
)
async def validate_config(
    body: str = Body(..., media_type="application/yaml"),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict[str, Any]:
    try:
        data = await asyncio.to_thread(
            load_bounded, body, get_settings().max_config_depth
        )
    except BoundedYAMLError as e:
        return {"ok": False, "errors": [str(e)]}
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["Top-level must be a mapping"]}
    plan = await config_io.import_config(session, data, apply=False)
    return plan.summary()


@router.post(
    "/config/import",
    summary="Apply a YAML config (atomic)",
    description=(
        "POST a YAML body with `?apply=true` to commit. Without "
        "`apply=true`, runs as a dry-run (same response shape as "
        "/validate). On apply: writes happen in a single transaction; "
        "any error rolls back the whole import.\n\n"
        "After successful apply, hot reloads the input manager + "
        "rule engine + schedule service so changes take effect "
        "immediately."
    ),
)
async def import_config_endpoint(
    body: str = Body(..., media_type="application/yaml"),
    apply: bool = Query(default=False, description="Set to true to commit"),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict[str, Any]:
    try:
        data = await asyncio.to_thread(
            load_bounded, body, get_settings().max_config_depth
        )
    except BoundedYAMLError as e:
        return {"ok": False, "errors": [str(e)]}
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["Top-level must be a mapping"]}

    plan = await config_io.import_config(session, data, apply=apply)

    if apply and plan.ok:
        # Record the change in the SAME transaction as the import (audit
        # A35): a config.import left no audit trail before. The summary is
        # counts + resource NAMES only — no secret values — so it is safe
        # to store redacted.
        from ...audit import record_change
        summary = plan.summary()
        await record_change(
            session, actor, "config.import",
            resource_kind="config", resource_id="pack",
            after={
                "creates": summary["creates"],
                "updates": summary["updates"],
                "warnings": summary["warnings"],
            },
        )
        await session.commit()
        # Hot reload the runtime so changes take effect now
        try:
            await get_manager().reload()
            await get_engine().reload_rules()
            # Audit A10: the tick only fires already-due schedules — it
            # does NOT recompute next_fire_at for an imported/changed cron.
            # Import nulls next_fire_at; recompute it here explicitly.
            from ...core.schedule_service import get_schedule_service
            await get_schedule_service().recompute_pending()
        except Exception:
            logger.exception("Hot reload after config import failed")
    elif not plan.ok or not apply:
        await session.rollback()

    summary = plan.summary()
    summary["applied"] = apply and plan.ok
    return summary
