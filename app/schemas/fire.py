"""``/v1/fire`` request/response shapes."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FireRequest(BaseModel):
    """Body for ``POST /v1/fire``."""

    type: str = Field(min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)
    test: bool = False
    source: str | None = Field(default=None, max_length=64)


class FireResponse(BaseModel):
    """Returned by both ``POST /v1/fire`` and rule-test endpoints."""

    id: str
    dispatched: bool
    channels: list[str]
    suppressed_reason: str | None = None
    # Settled outcome: sent | partial | failed | suppressed (audit A03).
    status: str = "sent"
    title: str
    message: str
    severity: str
