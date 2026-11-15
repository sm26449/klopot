"""``/v1/fire`` request/response shapes."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..utils.context_budget import check_context


class FireRequest(BaseModel):
    """Body for ``POST /v1/fire``."""

    type: str = Field(min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)
    test: bool = Field(default=False, description=(
        "Mark the notification as a test (shown with a Test badge, kept apart from real fires "
        "for de-duplication, sent without action buttons). With the `admin` scope the test also "
        "skips throttle, the delivery gate, quiet hours and de-duplication; with any other scope "
        "it is gated and counted like a real fire."))
    source: str | None = Field(default=None, max_length=64)
    # Episode lifecycle (optional). With an idempotency_key the fire belongs
    # to an episode: the first "firing" opens it and notifies, repeats while
    # it is open don't, "resolved" closes it (and sends resolved_type, if
    # given at opening). Keys are scoped to the caller.
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:@/-]+$",
    )
    status: Literal["firing", "resolved"] = "firing"
    resolved_type: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("context")
    @classmethod
    def _context_within_budget(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Stored, hashed and rendered for every fire — even of an unknown type
        # (utils/context_budget.py, public-exposure review).
        check_context(v, max_bytes=get_settings().fire_context_max_bytes)
        return v


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
    # Set when the fire carried an idempotency_key: the episode (incident) and
    # what happened to it — opened | repeat | resolved | stale | not_found.
    incident_id: str | None = None
    episode: str | None = None
