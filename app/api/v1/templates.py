"""``/v1/templates`` — template CRUD."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...core import rendering
from ...db import get_session
from ...db.models import Channel, Template, TemplateChannel
from ...schemas.common import ChannelKind, Page, Severity
from ...schemas.routing import RouteRead, RouteWrite
from ...schemas.template import TemplateCreate, TemplateRead, TemplateUpdate
from ...services.categories import canonical_category
from ...utils.like import like_escape
from ._crud import crud_list, flush_or_409

router = APIRouter()


async def _get_template_or_404(session: AsyncSession, type: str) -> Template:
    obj = (
        await session.execute(select(Template).where(Template.type == type))
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {type}",
        )
    return obj




@router.get("", response_model=Page[TemplateRead], summary="List templates")
async def list_templates(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    severity: Severity | None = None,
    enabled: bool | None = None,
    category: str | None = Query(
        default=None,
        description="Filter by category (e.g. 'Storage'). Pass '__none__' to "
                    "select uncategorized templates.",
    ),
    search: str | None = Query(
        default=None, description="Free-text match on type / title / category.",
    ),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[TemplateRead]:
    filters = []
    if severity is not None:
        filters.append(Template.severity == severity)
    if enabled is not None:
        filters.append(Template.enabled.is_(enabled))
    if category is not None:
        if category == "__none__":
            filters.append(Template.category.is_(None))
        else:
            filters.append(Template.category == category)
    if search:
        like = f"%{like_escape(search)}%"
        filters.append(or_(
            Template.type.like(like, escape="\\"),
            Template.title_template.like(like, escape="\\"),
            Template.category.like(like, escape="\\"),
        ))
    items, total = await crud_list(
        session, Template, skip=skip, limit=limit, filters=filters,
        order_by=Template.type,
    )
    return Page(
        items=[TemplateRead.model_validate(i) for i in items],
        total=total, limit=limit, offset=skip,
    )


@router.post(
    "", response_model=TemplateRead, status_code=status.HTTP_201_CREATED,
    summary="Create template",
)
async def create_template(
    body: TemplateCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> TemplateRead:
    data = body.model_dump(exclude={"require_pv_kw"})
    data["category"] = await canonical_category(session, data.get("category"))
    obj = Template(**data)
    session.add(obj)
    await flush_or_409(session, "Template create")
    await session.refresh(obj)
    await record_change(
        session, actor, "template.create",
        resource_kind="template", resource_id=obj.type,
        after=model_to_dict(obj),
    )
    await session.commit()
    return TemplateRead.model_validate(obj)


@router.get("/{type}", response_model=TemplateRead, summary="Get template")
async def get_template(
    type: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> TemplateRead:
    obj = (
        await session.execute(select(Template).where(Template.type == type))
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template not found: {type}")
    return TemplateRead.model_validate(obj)


@router.patch("/{type}", response_model=TemplateRead, summary="Update template")
async def update_template(
    type: str,
    body: TemplateUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> TemplateRead:
    obj = (
        await session.execute(select(Template).where(Template.type == type))
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template not found: {type}")
    before = model_to_dict(obj)
    changes = body.model_dump(exclude_unset=True, exclude={"require_pv_kw"})
    if changes.get("category"):
        changes["category"] = await canonical_category(session, changes["category"], exclude_type=type)
    for k, v in changes.items():
        setattr(obj, k, v)
    await flush_or_409(session, "Template update")
    await session.refresh(obj)
    await record_change(
        session, actor, "template.update",
        resource_kind="template", resource_id=obj.type,
        before=before, after=model_to_dict(obj),
    )
    await session.commit()
    return TemplateRead.model_validate(obj)


@router.delete("/{type}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete template")
async def delete_template(
    type: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    obj = (
        await session.execute(select(Template).where(Template.type == type))
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template not found: {type}")
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "template.delete",
        resource_kind="template", resource_id=type, before=before,
    )
    await session.commit()
    # 204 — no body


# ── Routing: template → channels (H-5) ─────────────────────────────


async def _routes_for(session: AsyncSession, template_id: int) -> list[RouteRead]:
    rows = (
        await session.execute(
            select(TemplateChannel, Channel)
            .join(Channel, Channel.id == TemplateChannel.channel_id)
            .where(TemplateChannel.template_id == template_id)
            .order_by(Channel.name)
        )
    ).all()
    from ...secrets_registry import mask_config
    return [
        RouteRead(
            channel_id=ch.id,
            channel_name=ch.name,
            kind=ChannelKind(ch.kind.value),
            severity_min=Severity(tc.severity_min.value),
            enabled=tc.enabled,
            # Route overrides are a partial channel config and can carry
            # secrets (e.g. a per-route auth_value). Redact them for the
            # read + audit paths using the channel's kind (audit F02); the
            # real values stay only in template_channels.channel_overrides.
            channel_overrides=mask_config("channel", ch.kind, tc.channel_overrides)
            if tc.channel_overrides else tc.channel_overrides,
        )
        for tc, ch in rows
    ]


@router.get(
    "/{type}/channels",
    response_model=list[RouteRead],
    summary="List the channels a template routes to",
)
async def list_template_channels(
    type: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> list[RouteRead]:
    tmpl = await _get_template_or_404(session, type)
    return await _routes_for(session, tmpl.id)


@router.put(
    "/{type}/channels",
    response_model=list[RouteRead],
    summary="Replace the full routing set for a template (atomic)",
    description=(
        "The body is the COMPLETE desired set of routes; channels absent "
        "from it are unlinked. Each item identifies its channel by "
        "``channel_id`` or ``channel_name``. Audited as ``route.set`` "
        "with the before/after route lists."
    ),
)
async def set_template_channels(
    type: str,
    routes: list[RouteWrite] = Body(...),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> list[RouteRead]:
    tmpl = await _get_template_or_404(session, type)
    before = [r.model_dump(mode="json") for r in await _routes_for(session, tmpl.id)]

    # Resolve + validate every referenced channel up front (all-or-nothing).
    resolved: dict[int, RouteWrite] = {}
    for r in routes:
        if r.channel_id is not None:
            ch = await session.get(Channel, r.channel_id)
        else:
            ch = (
                await session.execute(select(Channel).where(Channel.name == r.channel_name))
            ).scalar_one_or_none()
        if ch is None:
            ident = r.channel_id if r.channel_id is not None else r.channel_name
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown channel: {ident}",
            )
        if ch.id in resolved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Duplicate channel in route set: {ch.name}",
            )
        resolved[ch.id] = (r, ch.kind)

    from ...secrets_registry import merge_secret_update

    # Replace the set: drop existing links, insert the new ones. Capture
    # the old per-channel overrides first so a masked read echoed back
    # doesn't wipe a real secret (audit F02).
    old_overrides: dict[int, dict] = {}
    for tc in (
        await session.execute(
            select(TemplateChannel).where(TemplateChannel.template_id == tmpl.id)
        )
    ).scalars().all():
        old_overrides[tc.channel_id] = tc.channel_overrides or {}
        await session.delete(tc)
    await session.flush()
    for cid, (r, kind) in resolved.items():
        overrides = r.channel_overrides
        if overrides:
            overrides = merge_secret_update(
                "channel", kind, old_overrides.get(cid), overrides
            )
        session.add(TemplateChannel(
            template_id=tmpl.id,
            channel_id=cid,
            severity_min=r.severity_min,
            enabled=r.enabled,
            channel_overrides=overrides,
        ))

    await flush_or_409(session, "Set template routes")
    after_routes = await _routes_for(session, tmpl.id)
    await record_change(
        session, actor, "route.set",
        resource_kind="template", resource_id=tmpl.type,
        before={"routes": before},
        after={"routes": [r.model_dump(mode="json") for r in after_routes]},
    )
    await session.commit()
    return after_routes


@router.delete(
    "/{type}/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove one channel from a template's routing",
)
async def delete_template_channel(
    type: str,
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    tmpl = await _get_template_or_404(session, type)
    # Join the channel so we can mask the deleted route's overrides by its
    # kind, exactly as `_routes_for` does for the read/audit paths.
    row = (
        await session.execute(
            select(TemplateChannel, Channel.kind)
            .join(Channel, Channel.id == TemplateChannel.channel_id)
            .where(TemplateChannel.template_id == tmpl.id)
            .where(TemplateChannel.channel_id == channel_id)
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No route from {type} to channel {channel_id}",
        )
    tc, ch_kind = row
    # Route overrides are a partial channel config and can carry secrets
    # (e.g. a per-route auth_value). Mask them before they reach the audit
    # snapshot — otherwise a delete writes the plaintext a read-scoped key
    # could later retrieve from audit history (audit A-05).
    from ...secrets_registry import mask_config
    masked_overrides = (
        mask_config("channel", ch_kind, tc.channel_overrides)
        if tc.channel_overrides else tc.channel_overrides
    )
    before = {"channel_id": channel_id, "severity_min": tc.severity_min.value,
              "enabled": tc.enabled, "channel_overrides": masked_overrides}
    await session.delete(tc)
    await record_change(
        session, actor, "route.delete",
        resource_kind="template", resource_id=tmpl.type, before=before,
    )
    await session.commit()


# ── Preview (render without dispatch) ──────────────────────────────


@router.post(
    "/{type}/preview",
    summary="Render a template against a supplied context (no dispatch, no log)",
    description=(
        "Renders title + message with the given context. Placeholders "
        "that don't resolve are reported in ``missing_vars`` (and appear "
        "as ``[?name]`` in the rendered output). Pure function — nothing "
        "is dispatched or logged."
    ),
)
async def preview_template(
    type: str,
    body: dict[str, Any] | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> dict[str, Any]:
    tmpl = await _get_template_or_404(session, type)
    body = body or {}
    # Accept either {"context": {...}} or a bare context object.
    ctx = body.get("context", body) if isinstance(body, dict) else {}
    if not isinstance(ctx, dict):
        ctx = {}
    title, missing_title = rendering.render_with_missing(tmpl.title_template, ctx)
    message, missing_message = rendering.render_with_missing(tmpl.message_template, ctx)
    missing = sorted(set(missing_title + missing_message))
    return {"title": title, "message": message, "missing_vars": missing}
