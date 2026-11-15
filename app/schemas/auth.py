"""DTOs for ``/v1/auth`` (admin UI sessions)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .log import _as_utc_iso


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserRead(BaseModel):
    username: str
    role: str
    must_change_password: bool
    last_login_at: datetime | None = None
    password_changed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("last_login_at", "password_changed_at")
    def _utc(self, v: datetime | None) -> str | None:
        return _as_utc_iso(v)


class LoginResponse(BaseModel):
    user: UserRead
    # Also set as the ``alertd_csrf`` cookie; returned here so the SPA
    # can start sending ``X-CSRF-Token`` without parsing document.cookie.
    csrf_token: str


class SessionRead(BaseModel):
    id: int
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None = None
    user_agent: str | None = None
    current: bool = False

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "last_seen_at", "expires_at")
    def _utc(self, v: datetime) -> str | None:
        return _as_utc_iso(v)


class MeResponse(BaseModel):
    user: UserRead
    scopes: list[str]
    session: SessionRead
    # The address this request came from as Klopot sees it (behind a trusted
    # proxy: the client's, not the proxy's) — what an API key's source
    # allowlist is matched against.
    client_ip: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SessionsRevoked(BaseModel):
    revoked: int
