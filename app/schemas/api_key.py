"""API key DTOs.

Plaintext key value is returned ONCE on create + rotate. After that
the API only returns ``key_prefix`` (first 8 chars) so the operator
can identify which key did what without exposing the secret.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .log import _as_utc_iso

VALID_SCOPES = frozenset({"fire", "read", "ack", "admin"})


class ApiKeyBase(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    scopes: list[str] = Field(default_factory=lambda: ["fire"])
    expires_at: datetime | None = None
    enabled: bool = True


class ApiKeyCreate(ApiKeyBase):
    pass


class ApiKeyUpdate(BaseModel):
    scopes: list[str] | None = None
    expires_at: datetime | None = None
    enabled: bool | None = None


class ApiKeyRead(BaseModel):
    """Public read shape — never includes the plaintext key."""

    id: int
    name: str
    key_prefix: str  # safe to display
    scopes: list[str]
    enabled: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    rotated_from_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("expires_at", "last_used_at", "created_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so the expiry instant isn't read as local (F38).
        return _as_utc_iso(value)


class ApiKeyCreated(ApiKeyRead):
    """Returned ONCE on POST /v1/api_keys — includes plaintext key."""

    key: str  # plaintext: "alertd_..."
