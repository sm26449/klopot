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
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...config import get_settings
from ...core.engine import get_engine
from ...core.manager import get_manager
from ...db import get_session
from ...services import config_io, config_merge, packs
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
    sections: str | None = Query(
        default=None,
        description="Comma-separated subset: inputs, templates, channels, variables, rules, "
        "routes, schedules. Selecting templates includes their routes. Omit for everything.",
    ),
    category: str | None = Query(
        default=None,
        description="Keep templates of this category and rules whose template is in it "
        "(case-insensitive; '__none__' = uncategorized).",
    ),
    names: str | None = Query(
        default=None, description="Comma-separated identifiers to keep (template type, rule / variable name…).",
    ),
    with_dependencies: bool = Query(
        default=False, description="Close the selection over what it needs: templates, variables, inputs, "
        "inhibiting rules, gate variables, channels of its routes (docs/PACKS.md).",
    ),
    pack_id: str | None = Query(
        default=None, pattern=r"^[a-z][a-z0-9-]{1,63}$",
        description="Export as a pack: adds a `pack:` header with this id (secrets are always masked then).",
    ),
    pack_name: str | None = Query(default=None, max_length=120, description="Pack name (default: the id)."),
    pack_description: str | None = Query(default=None, max_length=1000),
    pack_version: str = Query(default="1.0.0", max_length=32),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> Response:
    selective = any(v is not None for v in (sections, category, names)) or with_dependencies
    if selective:
        section_list = _csv(sections)
        unknown = sorted(set(section_list or []) - set(config_merge.SECTIONS))
        if unknown:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"unknown section(s): {', '.join(unknown)}")
        data = await config_merge.export_selection(
            session, sections=section_list, category=category, names=_csv(names),
            with_dependencies=with_dependencies, mask_secrets=mask_secrets or pack_id is not None,
        )
        filename = "klopot-" + "-".join(k for k in data if k != "version") + ".yaml"
    else:
        data = await config_io.export_config(session, mask_secrets=mask_secrets or pack_id is not None)
        filename = "alertd-config.yaml"
    if pack_id is not None:
        header: dict[str, Any] = {"id": pack_id, "name": pack_name or pack_id}
        if pack_description:
            header["description"] = pack_description
        header["version"] = pack_version
        data = {"pack": header, **data}
        filename = f"{pack_id}.yaml"
    body = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True,
    )
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=body, media_type="application/yaml", headers=headers)


def _csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items or None


async def _load_pack(body: str) -> dict[str, Any] | str:
    """Parsed YAML mapping, or an error message.

    A ``pack:`` header (docs/PACKS.md) is accepted and dropped; a pack that
    declares parameters must be installed through /v1/packs, or its ``${…}``
    would be imported literally.
    """
    try:
        data = await asyncio.to_thread(load_bounded, body, get_settings().max_config_depth)
    except BoundedYAMLError as e:
        return str(e)
    if not isinstance(data, dict):
        return "Top-level must be a mapping"
    loaded: dict[str, Any] = data
    if "pack" in loaded:
        try:
            pack = packs.parse(loaded)
        except packs.PackError as e:
            return "; ".join(e.errors)
        if pack.header and pack.header.parameters:
            return (f"pack '{pack.header.id}' has parameters — install it with POST /v1/packs/apply "
                    "(or Admin UI → Packs) so they are filled in")
        loaded = pack.body
    return loaded


async def _record_and_reload(
    session: AsyncSession, actor: Actor, after: dict[str, Any], *, action: str = "config.import",
) -> None:
    """Audit the import in its own transaction, commit, hot-reload the runtime."""
    # Record the change in the SAME transaction as the import (audit A35).
    # Counts + resource NAMES only — no secret values.
    from ...audit import record_change
    await record_change(
        session, actor, action,
        resource_kind="config", resource_id="pack", after=after,
    )
    await session.commit()
    try:
        await get_manager().reload()
        await get_engine().reload_rules()
        # Audit A10: the tick only fires already-due schedules — it does NOT
        # recompute next_fire_at for an imported/changed cron.
        from ...core.schedule_service import get_schedule_service
        await get_schedule_service().recompute_pending()
    except Exception:
        logger.exception("Hot reload after config import failed")


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
    data = await _load_pack(body)
    if isinstance(data, str):
        return {"ok": False, "errors": [data]}

    plan = await config_io.import_config(session, data, apply=apply)

    if apply and plan.ok:
        summary = plan.summary()
        await _record_and_reload(session, actor, {
            "creates": summary["creates"],
            "updates": summary["updates"],
            "warnings": summary["warnings"],
        })
    elif not plan.ok or not apply:
        await session.rollback()

    summary = plan.summary()
    summary["applied"] = apply and plan.ok
    return summary


@router.post(
    "/config/import/preview",
    summary="Preview a pack item by item",
    description=(
        "POST a YAML pack (`application/yaml`). Every item is classified "
        "against the live configuration as `new`, `identical` or `differs` "
        "(with the changed fields, compared as import would store them), plus "
        "the validation `errors` / `warnings` of the whole pack. Writes nothing."
    ),
)
async def preview_import(
    body: str = Body(..., media_type="application/yaml"),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict[str, Any]:
    data = await _load_pack(body)
    if isinstance(data, str):
        return {"ok": False, "errors": [data], "warnings": [], "items": [], "counts": {}}
    preview = await config_merge.preview_import(session, data)
    await session.rollback()
    return preview.as_dict()


class ImportApply(BaseModel):
    yaml: str = Field(min_length=1, description="The pack, as YAML text.")
    decisions: dict[str, config_merge.Action] = Field(
        default_factory=dict,
        description='Per item, keyed "<section>:<key>" (e.g. "rules:soc_low"): overwrite, skip or copy. '
        "New items are imported unless skipped; identical ones are left alone.",
    )
    default_existing: config_merge.Action = Field(
        default="skip", description="Action for an existing item that differs and has no decision.",
    )


@router.post(
    "/config/import/apply",
    summary="Apply a pack with per-item choices (atomic)",
    description=(
        "Applies the pack after the per-item decisions: copies get a `_copy` "
        "name (a copied template takes the pack's rules / routes / schedules "
        "that point to it), skipped and identical items are left out. One "
        "transaction, audited as `config.import`, then a hot reload."
    ),
)
async def apply_import(
    body: ImportApply,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict[str, Any]:
    data = await _load_pack(body.yaml)
    if isinstance(data, str):
        return {"ok": False, "errors": [data], "applied": False}
    result = await config_merge.apply_import(session, data, body.decisions, body.default_existing)
    summary = result.summary()
    if result.plan.ok:
        await _record_and_reload(session, actor, {
            "created": result.created, "overwritten": result.overwritten,
            "skipped": result.skipped, "copied": result.copied,
            "warnings": summary["warnings"],
        })
    else:
        await session.rollback()
    summary["applied"] = result.plan.ok
    return summary
