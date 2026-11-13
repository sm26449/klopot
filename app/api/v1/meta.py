"""``/v1/meta`` — UI metadata (form schemas).

A read-only description of the fields every channel / input / variable
kind accepts, plus webhook presets. The admin UI generates all of its
typed forms from here so field lists live in exactly one place
(:mod:`app.meta_kinds`), not scattered across the JS.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...auth import Actor, require_scope
from ...meta_kinds import describe_kinds

router = APIRouter()


@router.get(
    "/meta/kinds",
    summary="Field schemas for channel/input/variable forms + webhook presets",
    description=(
        "The admin UI builds every typed form from this document. Each "
        "field carries name, type, required, secret, default and help; "
        "secret fields imply a ``<name>_ref`` env-reference sibling."
    ),
)
async def meta_kinds(
    actor: Actor = Depends(require_scope("read")),
) -> dict[str, Any]:
    return describe_kinds()
