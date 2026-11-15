"""``/v1/api_keys`` — API key management.

Plaintext key returned ONCE on create + rotate.
"""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import (
    Actor,
    generate_key_plaintext,
    hash_key_async,
    invalidate_key_cache,
    key_digest,
    require_scope,
)
from ...db import get_session
from ...db.models import ApiKey
from ...schemas.api_key import (
    VALID_SCOPES,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    ApiKeyUpdate,
)
from ...schemas.common import Page
from ...utils.time import to_naive_utc, utc_now
from ._crud import crud_get_or_404, crud_list, flush_or_409

router = APIRouter()

# Column width for ApiKey.name (see db/models.py). Rotation must keep the
# generated name within this bound (audit F27).
_NAME_COL_MAX = 64
# Strip a previously-appended rotation suffix so repeated rotations don't
# grow the name unboundedly. Matches both the legacy "-rotated-<ts>" and the
# new "-r<ts><rand>" shapes.
# Matches every scheme ever written: "-rotated-<ts>", "-r<14 digits><4 hex>"
# (until 2026-11-14) and "-r<14 digits><8 hex>".
_ROT_SUFFIX_RE = re.compile(r"-(?:rotated-\d+|r\d{14}(?:[0-9a-f]{8}|[0-9a-f]{4}))$")


def _rotated_name(old_name: str) -> str:
    """Build a bounded, collision-resistant name for a rotated key.

    The old scheme appended ``-rotated-YYYYMMDDHHMM`` (21 chars), which
    overflowed a valid 64-char name and collided on same-minute grace
    rotations. Strip any prior rotation suffix, cap the stable base, and
    append a second-precision timestamp plus random entropy so the result
    is always ≤ 64 chars and practically unique (audit F27).
    """
    base = _ROT_SUFFIX_RE.sub("", old_name)
    # 32 random bits: 16 gave a ~2 % chance of a clash among 50 rotations in
    # one second (birthday bound) — the collision test failed intermittently.
    suffix = utc_now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(4)  # 14+8
    return f"{base[:_NAME_COL_MAX - len(suffix) - 2]}-r{suffix}"


def _validate_scopes(scopes: list[str]):
    bad = [s for s in scopes if s not in VALID_SCOPES]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown scopes: {bad}. Valid: {sorted(VALID_SCOPES)}",
        )


@router.get("", response_model=Page[ApiKeyRead], summary="List API keys")
async def list_keys(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    enabled: bool | None = None,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> Page[ApiKeyRead]:
    filters = []
    if enabled is not None:
        filters.append(ApiKey.enabled.is_(enabled))
    items, total = await crud_list(
        session, ApiKey, skip=skip, limit=limit, filters=filters,
        order_by=ApiKey.name,
    )
    return Page(
        items=[ApiKeyRead.model_validate(i) for i in items],
        total=total, limit=limit, offset=skip,
    )


@router.post(
    "", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED,
    summary="Create API key (returns plaintext once)",
)
async def create_key(
    body: ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ApiKeyCreated:
    _validate_scopes(body.scopes)

    plaintext = generate_key_plaintext()
    obj = ApiKey(
        name=body.name,
        key_hash=await hash_key_async(plaintext),
        key_prefix=plaintext[:8],
        key_digest=key_digest(plaintext),
        scopes=body.scopes,
        enabled=body.enabled,
        expires_at=to_naive_utc(body.expires_at),
    )
    session.add(obj)
    await flush_or_409(session, "API key create")
    await session.refresh(obj)
    await record_change(
        session, actor, "api_key.create",
        resource_kind="api_key", resource_id=str(obj.id),
        after=model_to_dict(obj),
    )
    await session.commit()

    # Return plaintext exactly once
    return ApiKeyCreated(
        **ApiKeyRead.model_validate(obj).model_dump(),
        key=plaintext,
    )


@router.get("/{key_id}", response_model=ApiKeyRead, summary="Get API key (no plaintext)")
async def get_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ApiKeyRead:
    obj = await crud_get_or_404(session, ApiKey, key_id)
    return ApiKeyRead.model_validate(obj)


@router.patch("/{key_id}", response_model=ApiKeyRead, summary="Update API key metadata")
async def update_key(
    key_id: int,
    body: ApiKeyUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ApiKeyRead:
    obj = await crud_get_or_404(session, ApiKey, key_id)
    if body.scopes is not None:
        _validate_scopes(body.scopes)
    before = model_to_dict(obj)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await flush_or_409(session, "API key update")
    await session.refresh(obj)
    await record_change(
        session, actor, "api_key.update",
        resource_kind="api_key", resource_id=str(obj.id),
        before=before, after=model_to_dict(obj),
    )
    await session.commit()
    # Scope / enabled / expiry changes must take effect on the next
    # request, not after the 30s resolve cache expires.
    invalidate_key_cache(obj.id)
    return ApiKeyRead.model_validate(obj)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke API key")
async def delete_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    obj = await crud_get_or_404(session, ApiKey, key_id)
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "api_key.delete",
        resource_kind="api_key", resource_id=str(key_id), before=before,
    )
    await session.commit()
    invalidate_key_cache(key_id)


@router.post(
    "/{key_id}/rotate",
    response_model=ApiKeyCreated,
    summary="Rotate (issue a new plaintext key, revoke the old)",
)
async def rotate_key(
    key_id: int,
    grace_sec: int = Query(
        default=0, ge=0, le=600,
        description="Keep the old key valid for this many seconds (grace "
                    "period) instead of revoking it immediately.",
    ),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ApiKeyCreated:
    from datetime import timedelta

    old = await crud_get_or_404(session, ApiKey, key_id)
    if not old.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rotate a disabled key",
        )

    plaintext = generate_key_plaintext()
    new = ApiKey(
        name=_rotated_name(old.name),
        key_hash=await hash_key_async(plaintext),
        key_prefix=plaintext[:8],
        key_digest=key_digest(plaintext),
        scopes=list(old.scopes),
        enabled=True,
        expires_at=old.expires_at,
        rotated_from_id=old.id,
    )
    if grace_sec > 0:
        # Grace period: leave the old key enabled but expiring soon, so
        # in-flight callers keep working while they pick up the new key
        # (docs/AUTH_MODEL.md). The resolver honours expires_at.
        grace_expiry = utc_now() + timedelta(seconds=grace_sec)
        if old.expires_at is None or old.expires_at > grace_expiry:
            old.expires_at = grace_expiry
    else:
        old.enabled = False
    session.add(new)
    await flush_or_409(session, "API key rotate")
    await session.refresh(new)
    await record_change(
        session, actor, "api_key.rotate",
        resource_kind="api_key", resource_id=str(new.id),
        before={"old_id": old.id, "old_name": old.name, "grace_sec": grace_sec},
        after=model_to_dict(new),
    )
    await session.commit()
    invalidate_key_cache(old.id)
    return ApiKeyCreated(
        **ApiKeyRead.model_validate(new).model_dump(),
        key=plaintext,
    )
