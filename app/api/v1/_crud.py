"""Generic CRUD helpers shared by resource routers.

Each resource router uses these to keep handlers small and uniform:

    return await crud_list(session, Template, skip, limit)
    obj = await crud_get_or_404(session, Template, id)

Pagination is built into ``crud_list``. Filters are applied before
counting + slicing.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from ...schemas.common import Page

logger = logging.getLogger(__name__)



async def crud_list[T: DeclarativeBase](
    session: AsyncSession,
    model: type[T],
    *,
    skip: int = 0,
    limit: int = 50,
    filters: list[Any] | None = None,
    order_by: Any | None = None,
) -> tuple[list[T], int]:
    """Paged + filtered list with total count.

    Returns (items, total). Caller wraps in ``Page`` schema.
    """
    base = select(model)
    count_q = select(func.count()).select_from(model)
    if filters:
        for f in filters:
            base = base.where(f)
            count_q = count_q.where(f)
    if order_by is not None:
        # Accept either a single column or a list/tuple of columns
        if isinstance(order_by, list | tuple):
            base = base.order_by(*order_by)
        else:
            base = base.order_by(order_by)
    base = base.offset(skip).limit(limit)

    items = list((await session.execute(base)).scalars().all())
    total = (await session.execute(count_q)).scalar_one()
    return items, total


def page_response(items: list[Any], total: int, skip: int, limit: int) -> dict[str, Any]:
    """Standard pagination envelope as a dict (Pydantic Page wraps later)."""
    return {"items": items, "total": total, "limit": limit, "offset": skip}


async def crud_get_or_404[T: DeclarativeBase](session: AsyncSession, model: type[T], id_value: Any) -> T:
    """Fetch by primary key or raise 404."""
    obj = await session.get(model, id_value)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} not found: {id_value}",
        )
    return obj


async def enforce_create_cap[T: DeclarativeBase](
    session: AsyncSession, model: type[T], cap: int, *, entity: str, n_new: int = 1,
) -> None:
    """Refuse a create that would push ``model``'s total row count past ``cap``
    (audit D-02/A-14).

    ``cap <= 0`` disables the limit. The count is of ALL rows (enabled and
    disabled), matching NFR's "total" wording; ``n_new`` is how many rows the
    operation adds (1 for a single REST create, N for a batch/import), so this
    runs BEFORE the rows are added. Raises 409 ``LIMIT_REACHED`` with the limit
    and current count so a client (and the admin UI) can explain it.
    """
    if cap <= 0:
        return
    current = (await session.execute(select(func.count()).select_from(model))).scalar_one()
    if current + n_new > cap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LIMIT_REACHED",
                "message": (
                    f"{entity} limit of {cap} reached ({current} already exist); "
                    f"raise the configured limit to add more"
                ),
                "entity": entity,
                "limit": cap,
                "current": current,
            },
        )


def _conflict(action: str, e: IntegrityError) -> HTTPException:
    """A 409 that says what went wrong in the operator's terms. The driver's
    text (``(1062, "Duplicate entry 'x' for key 'uq_…'")``) names tables,
    keys and values; it goes to the log, not the response (review F12)."""
    raw = str(e.orig) if e.orig else str(e)
    logger.info("%s refused by the database: %s", action, raw[:500])
    code = e.orig.args[0] if e.orig is not None and getattr(e.orig, "args", None) else None
    text = raw.lower()
    if code == 1062 or "unique constraint" in text or "duplicate" in text:
        reason = "one with the same name or key already exists"
    elif code in (1451, 1452) or "foreign key" in text:
        reason = "it refers to something that does not exist, or something still uses it"
    else:
        reason = "the database refused the change"
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{action} failed: {reason}")


async def commit_or_409(session: AsyncSession, action: str = "operation") -> None:
    """Commit and translate IntegrityError to 409 Conflict."""
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise _conflict(action, e) from e


async def flush_or_409(session: AsyncSession, action: str = "operation") -> None:
    """Flush (not commit) and translate IntegrityError to 409 Conflict.

    Lets a handler detect a uniqueness/FK conflict without ending the
    transaction, so the change and its audit row can be committed together
    in one transaction (audit A35: the audit snapshot must be atomic with
    the change, not a second commit after it)."""
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise _conflict(action, e) from e


__all__ = [
    "Page",
    "commit_or_409",
    "crud_get_or_404",
    "crud_list",
    "enforce_create_cap",
    "flush_or_409",
    "page_response",
]
