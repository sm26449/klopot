"""API key DTOs.

Plaintext key value is returned ONCE on create + rotate. After that
the API only returns ``key_prefix`` (first 8 chars) so the operator
can identify which key did what without exposing the secret.
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from ..utils.client_ip import parse_networks
from .log import _as_utc_iso

VALID_SCOPES = frozenset({"fire", "read", "ack", "admin"})
MAX_ALLOWED_CIDRS = 64
MAX_RATE_LIMIT_PER_MIN = 60_000   # 1000 a second: above that a limit means nothing
MAX_ALLOWED_TYPES = 64
# A template type (^[a-z][a-z0-9_]*$) or an fnmatch pattern over types.
_TYPE_PATTERN = re.compile(r"^[a-z0-9_*?\[\]!-]{1,64}$")

_RATE_LIMIT_DOC = (
    "Requests a minute the key may make; null = no limit. A quiet key may send this many at once, "
    "then one every 60/N seconds. Over it: 429 with Retry-After."
)

_ALLOWED_TYPES_DOC = (
    "Alert types the key may fire through POST /v1/fire: template types or patterns like backup_*. "
    "Empty = every type. Another type (or resolved_type) gets 403."
)

_ALLOWED_CIDRS_DOC = (
    "Addresses the key may be used from: IPs or CIDRs (IPv4 and IPv6). Empty = any address. "
    "A request from elsewhere gets 403 and counts as a wrong key for that address."
)


def normalize_allowed_cidrs(entries: list[str]) -> list[str]:
    """Validated, canonical (``10.0.0.0/24`` for ``10.0.0.7/24``) and
    de-duplicated, in the order given. A /0 is refused: empty already means
    any address, and an explicit catch-all hides that the key is open."""
    if len(entries) > MAX_ALLOWED_CIDRS:
        raise ValueError(f"at most {MAX_ALLOWED_CIDRS} addresses or networks")
    nets = parse_networks(tuple(entries), label="address",
                          catch_all="allows every address; leave the list empty for that")
    return list(dict.fromkeys(str(n) for n in nets))


# A bracket class (``[a-z]``, ``[!0]``): no literal character of the type.
_CLASS = re.compile(r"\[[^\]]*\]")


def normalize_allowed_types(entries: list[str]) -> list[str]:
    """Trimmed, lowercase-only, de-duplicated in the order given. A pattern
    with no literal character — only ``*``, ``?`` and ``[…]`` classes, such
    as ``*`` or ``[a-z]*`` — is refused: it names no type, matches every
    type (or nearly), and would show the key as restricted while it is open
    (2026-11-17 changes review, CR-05). Empty already means every type."""
    if len(entries) > MAX_ALLOWED_TYPES:
        raise ValueError(f"at most {MAX_ALLOWED_TYPES} types or patterns")
    out = []
    for raw in entries:
        entry = raw.strip()
        if not _TYPE_PATTERN.match(entry):
            raise ValueError(f"{raw!r} is not a template type or a pattern like backup_*")
        if not _CLASS.sub("", entry).strip("*?"):
            raise ValueError(f"{raw!r} names no type (only wildcards); leave the list empty to allow every type")
        out.append(entry)
    return list(dict.fromkeys(out))


class ApiKeyBase(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    scopes: list[str] = Field(default_factory=lambda: ["fire"])
    expires_at: datetime | None = None
    enabled: bool = True
    allowed_cidrs: list[str] = Field(default_factory=list, description=_ALLOWED_CIDRS_DOC)
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=MAX_RATE_LIMIT_PER_MIN,
                                           description=_RATE_LIMIT_DOC)
    allowed_types: list[str] = Field(default_factory=list, description=_ALLOWED_TYPES_DOC)

    @field_validator("allowed_cidrs")
    @classmethod
    def _cidrs(cls, v: list[str]) -> list[str]:
        return normalize_allowed_cidrs(v)

    @field_validator("allowed_types")
    @classmethod
    def _types(cls, v: list[str]) -> list[str]:
        return normalize_allowed_types(v)


class ApiKeyCreate(ApiKeyBase):
    pass


class ApiKeyUpdate(BaseModel):
    scopes: list[str] | None = None
    expires_at: datetime | None = None
    enabled: bool | None = None
    allowed_cidrs: list[str] | None = Field(default=None, description=_ALLOWED_CIDRS_DOC)
    # Sent as null: remove the limit (an omitted field leaves it as it is).
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=MAX_RATE_LIMIT_PER_MIN,
                                           description=_RATE_LIMIT_DOC)
    allowed_types: list[str] | None = Field(default=None, description=_ALLOWED_TYPES_DOC)

    @field_validator("allowed_cidrs")
    @classmethod
    def _cidrs(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else normalize_allowed_cidrs(v)

    @field_validator("allowed_types")
    @classmethod
    def _types(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else normalize_allowed_types(v)


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
    allowed_cidrs: list[str] = Field(default_factory=list, description=_ALLOWED_CIDRS_DOC)
    rate_limit_per_min: int | None = Field(default=None, description=_RATE_LIMIT_DOC)
    allowed_types: list[str] = Field(default_factory=list, description=_ALLOWED_TYPES_DOC)
    rotated_from_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("allowed_cidrs", "allowed_types", mode="before")
    @classmethod
    def _null_is_any(cls, v: list[str] | None) -> list[str]:
        return list(v or [])

    @field_serializer("expires_at", "last_used_at", "created_at")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        # Z-suffixed UTC so the expiry instant isn't read as local (F38).
        return _as_utc_iso(value)


class ApiKeyCreated(ApiKeyRead):
    """Returned ONCE on POST /v1/api_keys — includes plaintext key."""

    key: str  # plaintext: "alertd_..."
