"""Shared schema types. The enums are defined once in ``app.enums`` (no
SQLAlchemy there, so the API layer still does not pull in the ORM) and shared
with the database models; they are re-exported here for the schemas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# The enums live in app.enums (shared with the models); explicit re-exports.
from ..enums import ChannelKind as ChannelKind
from ..enums import InputKind as InputKind
from ..enums import Severity as Severity
from ..enums import SnoozeScope as SnoozeScope
from ..enums import SuppressedReason as SuppressedReason
from ..enums import VariableSource as VariableSource

# ── Pagination envelope ────────────────────────────────────────────


class Page[T](BaseModel):
    """Standard paginated list response.

    Used by every ``GET /v1/<resource>`` endpoint that returns a
    list. Clients can paginate with ``?limit=N&offset=M``.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(from_attributes=True)


# ── Error envelope ─────────────────────────────────────────────────


class ErrorBody(BaseModel):
    """Per-API_DESIGN.md error model. Clients receive this on 4xx/5xx."""

    code: str
    message: str
    details: dict | None = None
    trace_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
