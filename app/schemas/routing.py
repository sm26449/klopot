"""Routing DTOs — template → channel links (``template_channels``).

Used by:
- ``GET  /v1/templates/{type}/channels`` → list of :class:`RouteRead`
- ``PUT  /v1/templates/{type}/channels`` → atomic set-replacement, body
  is a list of :class:`RouteWrite`
- ``GET  /v1/channels/{id}/usage`` → :class:`ChannelUsage`

A route refers to its channel by ``channel_id`` OR ``channel_name`` on
write (whichever the client holds); reads always carry both.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from .common import ChannelKind, Severity


class RouteWrite(BaseModel):
    """One desired route in a ``PUT .../channels`` set."""

    channel_id: int | None = None
    channel_name: str | None = None
    severity_min: Severity = Severity.info
    enabled: bool = True
    channel_overrides: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _need_identifier(self) -> RouteWrite:
        if self.channel_id is None and not self.channel_name:
            raise ValueError("channel_id or channel_name is required")
        return self


class RouteRead(BaseModel):
    """One existing route (template ⇄ channel)."""

    channel_id: int
    channel_name: str
    kind: ChannelKind
    severity_min: Severity
    enabled: bool
    channel_overrides: dict[str, Any] | None = None


class ChannelUsageTemplate(BaseModel):
    type: str
    severity_min: Severity
    enabled: bool


class ChannelUsage(BaseModel):
    """Which templates route to a channel — blocks deletion when non-empty."""

    channel_id: int
    channel_name: str
    templates: list[ChannelUsageTemplate] = Field(default_factory=list)
