"""Packs (docs/PACKS.md): the built-in catalog, preview and install.

A pack comes from the catalog (``pack_id``) or from the caller (``yaml``).
Its parameters are checked and substituted, then the rendered document goes
through the same preview / per-item apply as ``/v1/config/import/*``.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...config import get_settings
from ...db.session import get_session
from ...services import config_merge, packs
from .config import _record_and_reload

router = APIRouter()

LocalText = str | dict[str, str]


class PackParameterOut(BaseModel):
    name: str
    label: LocalText | None = None
    description: LocalText | None = None
    type: str
    default: Any = None
    required: bool
    example: Any = None


class PackSummary(BaseModel):
    id: str | None = Field(description="Null for a pack without a header.")
    name: LocalText | None = Field(description='A string, or texts by language: {"en": …, "ro": …}.')
    description: LocalText | None = None
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    parameters: list[PackParameterOut] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict, description="Items per section.")


class PackList(BaseModel):
    items: list[PackSummary]


class PackDetail(PackSummary):
    yaml: str


class PackInspect(PackSummary):
    ok: bool
    errors: list[str] = Field(default_factory=list)


class PackSource(BaseModel):
    pack_id: str | None = Field(default=None, description="A catalog pack (GET /v1/packs).")
    yaml: str | None = Field(default=None, min_length=1, description="Your own pack, as YAML text.")
    params: dict[str, Any] = Field(default_factory=dict, description="Parameter values by name; omitted ones take their default.")

    @model_validator(mode="after")
    def _one_source(self) -> PackSource:
        if (self.pack_id is None) == (self.yaml is None):
            raise ValueError("give exactly one of pack_id or yaml")
        return self


class PackApply(PackSource):
    decisions: dict[str, config_merge.Action] = Field(
        default_factory=dict, description='Per item "<section>:<key>": overwrite, skip or copy (as /v1/config/import/apply).',
    )
    default_existing: config_merge.Action = Field(default="skip", description="Action for an existing item that differs.")


async def _load(source: PackSource) -> packs.Pack:
    if source.pack_id is not None:
        pack = packs.catalog().get(source.pack_id)
        if pack is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Pack not found: {source.pack_id}")
        return pack
    return await asyncio.to_thread(packs.parse, source.yaml or "", max_depth=get_settings().max_config_depth)


async def _render(source: PackSource) -> packs.Rendered | list[str]:
    try:
        return packs.render(await _load(source), source.params)
    except packs.PackError as e:
        return e.errors


@router.get("", response_model=PackList, summary="List the built-in packs")
async def list_packs(actor: Actor = Depends(require_scope("read"))) -> PackList:
    return PackList.model_validate({"items": [p.summary() for p in packs.catalog().values()]})


@router.get("/{pack_id}", response_model=PackDetail, summary="Get a built-in pack (summary + YAML)")
async def get_pack(pack_id: str, actor: Actor = Depends(require_scope("read"))) -> PackDetail:
    pack = packs.catalog().get(pack_id)
    if pack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Pack not found: {pack_id}")
    return PackDetail.model_validate({**pack.summary(), "yaml": packs.catalog_text(pack_id)})


@router.post(
    "/inspect",
    response_model=PackInspect,
    response_model_exclude_none=False,
    summary="Read a pack's header and parameters",
    description="For a pack file the caller has: its summary (name, parameters, counts) without validating the body.",
)
async def inspect_pack(body: PackSource, actor: Actor = Depends(require_scope("admin"))) -> PackInspect:
    try:
        pack = await _load(body)
    except packs.PackError as e:
        return PackInspect(ok=False, errors=e.errors, id=None, name=None)
    return PackInspect.model_validate({"ok": True, "errors": [], **pack.summary()})


@router.post(
    "/preview",
    summary="Preview installing a pack",
    description=(
        "Substitutes the parameters, then classifies every item as `new`, `identical` or "
        "`differs` against the live configuration, like /v1/config/import/preview. Writes nothing."
    ),
)
async def preview_pack(
    body: PackSource,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict[str, Any]:
    rendered = await _render(body)
    if isinstance(rendered, list):
        return {"ok": False, "errors": rendered, "warnings": [], "items": [], "counts": {}}
    preview = await config_merge.preview_import(session, rendered.document)
    await session.rollback()
    return {**preview.as_dict(), "pack": rendered.pack.summary(), "params": rendered.params,
            "env": _env_status(rendered)}


def _env_status(rendered: packs.Rendered) -> list[dict[str, Any]]:
    """For each `env` parameter: may Klopot resolve that variable, and is it set?
    (The value itself is never returned.)"""
    import os

    settings = get_settings()
    out = []
    for p in rendered.pack.header.parameters if rendered.pack.header else []:
        if p.type != "env":
            continue
        name = str(rendered.params.get(p.name) or "")
        out.append({"param": p.name, "name": name, "allowed": settings.secret_ref_allowed(name),
                    "set": bool(name and os.environ.get(name))})
    return out


@router.post(
    "/apply",
    summary="Install a pack (atomic)",
    description=(
        "Substitutes the parameters and applies the pack with per-item decisions, like "
        "/v1/config/import/apply: one transaction, audited as `pack.install`, then a hot reload."
    ),
)
async def apply_pack(
    body: PackApply,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict[str, Any]:
    rendered = await _render(body)
    if isinstance(rendered, list):
        return {"ok": False, "errors": rendered, "applied": False}
    result = await config_merge.apply_import(session, rendered.document, body.decisions, body.default_existing)
    summary = result.summary()
    if result.plan.ok:
        h = rendered.pack.header
        await _record_and_reload(session, actor, {
            "pack": {"id": h.id, "version": h.version} if h else None,
            "params": rendered.params,
            "created": result.created, "overwritten": result.overwritten,
            "skipped": result.skipped, "copied": result.copied, "warnings": summary["warnings"],
        }, action="pack.install")
    else:
        await session.rollback()
    summary["applied"] = result.plan.ok
    return summary
