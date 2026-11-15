"""Read-scoped operational visibility."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Actor, require_scope
from ...core.operations import snapshot
from ...db import get_session
from ...schemas.operations import OperationsRead

router = APIRouter()


@router.get("/operations", response_model=OperationsRead, summary="Queues and background workers")
async def operations(session: AsyncSession = Depends(get_session),
                     actor: Actor = Depends(require_scope("read"))) -> OperationsRead:
    return await snapshot(session)
