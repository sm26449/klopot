"""``/v1/variables`` — variable CRUD."""
from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...core.manager import VariableConfigError, dry_compile_variable, get_manager
from ...core.staleness import effective_stale_after_sec
from ...core.state_cache import get_state_cache
from ...db import get_session
from ...db.models import Variable
from ...schemas.common import Page, VariableSource
from ...schemas.variable import VariableCreate, VariableRead, VariableUpdate
from ...utils.like import like_escape
from ._crud import crud_list, flush_or_409

router = APIRouter()


def _reject_uncompilable_config(
    source: VariableSource, config: dict, name: str, input_id: int | None
) -> None:
    """422 if the variable's config can't compile into a runtime mapping — so a
    reload-breaking config is refused before anything is committed (audit V09),
    instead of persisting the row and failing the hot reload with a 500."""
    try:
        dry_compile_variable(source, config, name, input_id)
    except VariableConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid variable config for source {source.value!r}: {e}",
        ) from e


def _stale_after_sec(var: Variable) -> int | None:
    """Resolved staleness window for a variable, or None for 'never stale'.

    Uses the single source-aware policy the runtime mapping applies
    (``core.staleness.effective_stale_after_sec``) so the API's ``is_stale``
    can never disagree with how the engine actually treats the value
    (audit F31): constants and schedule slots latch (never stale); other
    sources default to 300 s when no explicit window is configured.
    """
    cfg = var.config or {}
    return effective_stale_after_sec(var.source, cfg.get("stale_after_sec"))


def _to_read(var: Variable) -> VariableRead:
    """Serialize a Variable + attach live runtime state from the cache.

    Decoupled so list/get/create/update all return the same shape."""
    out = VariableRead.model_validate(var)
    snap = get_state_cache().get(var.name)
    if snap is None:
        return out
    now_mono = time.monotonic()
    out.last_value = snap.value
    # UTC-aware, not naive local time, so the wire value is unambiguous (F38).
    out.last_value_at = datetime.fromtimestamp(snap.wall_ts, UTC)
    age = snap.age_sec(now=now_mono)
    out.age_sec = round(age, 3)
    window = _stale_after_sec(var)
    out.is_stale = False if window is None else age > window
    return out


@router.get("", response_model=Page[VariableRead], summary="List variables")
async def list_variables(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    source: VariableSource | None = None,
    enabled: bool | None = None,
    stale: bool | None = Query(
        default=None,
        description="Filter on live staleness (runtime, not a DB column).",
    ),
    search: str | None = Query(
        default=None, description="Free-text match on name / description.",
    ),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[VariableRead]:
    from sqlalchemy import or_

    filters = []
    if source is not None:
        filters.append(Variable.source == source)
    if enabled is not None:
        filters.append(Variable.enabled.is_(enabled))
    if search:
        like = f"%{like_escape(search)}%"
        filters.append(or_(
            Variable.name.like(like, escape="\\"),
            Variable.description.like(like, escape="\\"),
        ))

    if stale is None:
        # Fast path: staleness isn't involved, paginate in SQL.
        items, total = await crud_list(
            session, Variable, skip=skip, limit=limit, filters=filters,
            order_by=Variable.name,
        )
        return Page(
            items=[_to_read(i) for i in items],
            total=total, limit=limit, offset=skip,
        )

    # Staleness is a runtime property (state cache), not a DB column, so
    # we must materialize the SQL-filtered set, serialize (attaching live
    # state), filter on is_stale, then paginate in Python. The variable
    # table is small (≤ a few hundred rows) so this stays cheap.
    all_items, _ = await crud_list(
        session, Variable, skip=0, limit=500, filters=filters,
        order_by=Variable.name,
    )
    reads = [_to_read(i) for i in all_items]
    reads = [r for r in reads if r.is_stale is stale]
    total = len(reads)
    page = reads[skip:skip + limit]
    return Page(items=page, total=total, limit=limit, offset=skip)


@router.post(
    "", response_model=VariableRead, status_code=status.HTTP_201_CREATED,
    summary="Create variable",
)
async def create_variable(
    body: VariableCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> VariableRead:
    _reject_uncompilable_config(body.source, body.config, body.name, body.input_id)
    obj = Variable(**body.model_dump())
    session.add(obj)
    await flush_or_409(session, "Variable create")
    await session.refresh(obj)
    await record_change(
        session, actor, "variable.create",
        resource_kind="variable", resource_id=obj.name,
        after=model_to_dict(obj),
    )
    await session.commit()
    await get_manager().reload()
    return _to_read(obj)


@router.get("/{name}", response_model=VariableRead, summary="Get variable by name")
async def get_variable(
    name: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> VariableRead:
    from sqlalchemy import select
    obj = (
        await session.execute(select(Variable).where(Variable.name == name))
    ).scalar_one_or_none()
    if obj is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variable not found: {name}")
    return _to_read(obj)


@router.patch("/{name}", response_model=VariableRead, summary="Update variable")
async def update_variable(
    name: str,
    body: VariableUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> VariableRead:
    from sqlalchemy import select
    obj = (
        await session.execute(select(Variable).where(Variable.name == name))
    ).scalar_one_or_none()
    if obj is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variable not found: {name}")
    before = model_to_dict(obj)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    # Validate the MERGED config against the effective source (which a PATCH may
    # or may not change) before writing — a reload-breaking config must never be
    # committed (audit V09).
    _reject_uncompilable_config(obj.source, obj.config, obj.name, obj.input_id)
    await flush_or_409(session, "Variable update")
    await session.refresh(obj)
    await record_change(
        session, actor, "variable.update",
        resource_kind="variable", resource_id=obj.name,
        before=before, after=model_to_dict(obj),
    )
    await session.commit()
    await get_manager().reload()
    return _to_read(obj)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete variable")
async def delete_variable(
    name: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    from sqlalchemy import select
    obj = (
        await session.execute(select(Variable).where(Variable.name == name))
    ).scalar_one_or_none()
    if obj is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variable not found: {name}")
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "variable.delete",
        resource_kind="variable", resource_id=name, before=before,
    )
    await session.commit()
    await get_manager().reload()
