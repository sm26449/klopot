"""Authentication — API keys (machines) and browser sessions (humans).

FastAPI dependency: ``Depends(require_scope("admin"))`` etc. Resolves
the caller from, in order:

1. ``X-API-Key`` header → bcrypt-verified row in ``api_keys``
   (service-to-service; scopes from the row).
2. ``alertd_session`` cookie → row in ``admin_sessions`` (admin UI;
   scope ``admin``). Cookie-authenticated *writes* must also pass the
   CSRF checks (``X-CSRF-Token`` double-submit + ``Sec-Fetch-Site`` /
   ``Origin``) and are refused while the account has
   ``must_change_password`` set — see docs/AUTH_MODEL.md.

Either way an ``Actor`` lands on ``request.state.actor``; handlers
only ever see ``require_scope``.

Scope hierarchy (per docs/AUTH_MODEL.md):
- ``admin`` implies all other scopes.
- Multiple scopes per key are additive (e.g. ``["fire", "read"]``).
"""
from __future__ import annotations

import hmac
import ipaddress
import math
import re
from collections import OrderedDict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from urllib.parse import urlsplit

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .db.models import AdminSession, AdminUser, ApiKey
from .utils.client_ip import Network, in_networks, parse_networks, real_client_ip
from .utils.rate_limit import PerMinuteLimiter
from .utils.time import utc_now

_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API key — see /v1/api_keys to create one. Format: alertd_<random>",
)


def scope_grants(scopes: Collection[str], required: str) -> bool:
    """The one place the scope hierarchy lives: ``admin`` implies every other
    scope, otherwise the exact scope must be present. Used by ``Actor.has_scope``
    and by any check that works off a raw scope collection (e.g. the WebSocket
    revalidation in ``api/v1/state.py`` — audit A-13) so they never diverge."""
    return required in scopes or "admin" in scopes


@dataclass
class Actor:
    """Identifies the caller for audit + scope checks."""

    kind: str  # "api_key" / "user" / "system" ("jwt" reserved)
    id: int | None
    name: str
    scopes: frozenset[str]
    session_id: int | None = None  # admin_sessions.id for kind="user"
    # An API key's source allowlist (api_keys.allowed_cidrs), parsed; empty =
    # any address. Kept on the cached actor so every request — a cache hit
    # too — is checked against its own client address (_source_allowed).
    allowed_networks: tuple[Network, ...] = ()
    # An API key's own limit (api_keys.rate_limit_per_min); None = no limit.
    rate_limit_per_min: int | None = None

    def has_scope(self, required: str) -> bool:
        """``admin`` implies all other scopes."""
        return scope_grants(self.scopes, required)

    @property
    def is_user(self) -> bool:
        return self.kind == "user"


# ── bcrypt cache (audit M-7) ─────────────────────────────────────────
# Every API request runs through _resolve_key, which scans the prefix
# bucket and bcrypt-verifies each candidate row. bcrypt cost=12 = ~250ms
# of CPU per request — the UI polling /v1/log every few seconds was
# saturating one gunicorn worker thread.
#
# Cache the (raw_key → Actor) mapping for 30s after a successful
# resolve. We hash the raw key with sha256 to avoid keeping plaintext
# around in process memory; the hash is unique to the key but reveals
# nothing on dump. On invalid keys we DON'T cache (otherwise a stuck
# bad caller would never get re-checked against the DB).
#
# Trade-off: last_used_at lags by up to ``_KEY_CACHE_TTL_SEC`` on cached
# hits. For audit purposes that's fine; if granular accuracy matters
# in future, batch the updates.
import hashlib as _hashlib  # noqa: E402 — section-local import, see comment above
import threading as _threading  # noqa: E402
import time as _time  # noqa: E402

# Each entry is (cached_at_monotonic, actor, key_expires_at). The third
# element is the API key's own ``expires_at`` (None = never expires) so a
# cache hit can reject a key that has passed its expiry even though the
# 30 s cache TTL hasn't lapsed — mirrors the session cache (audit A33).
_KEY_CACHE: dict[str, tuple[float, Actor, datetime | None]] = {}
_KEY_CACHE_LOCK = _threading.Lock()
_KEY_CACHE_TTL_SEC = 30.0
_KEY_CACHE_MAX = 100  # cap to bound memory; LRU isn't worth the code
# Monotonic revocation generation (audit F05). Bumped on every
# disable/delete/rotate invalidation. A verify that started before a
# revocation (gen captured pre-read) must not fill the cache afterwards,
# or an in-flight bcrypt would restore a just-revoked key for the TTL.
_KEY_CACHE_GENERATION = 0


def _key_cache_generation() -> int:
    with _KEY_CACHE_LOCK:
        return _KEY_CACHE_GENERATION


def _key_cache_fingerprint(raw: str) -> str:
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _key_cache_get(raw: str) -> Actor | None:
    fp = _key_cache_fingerprint(raw)
    now = _time.monotonic()
    with _KEY_CACHE_LOCK:
        entry = _KEY_CACHE.get(fp)
        if entry is None:
            return None
        ts, actor, expires_at = entry
        if now - ts > _KEY_CACHE_TTL_SEC:
            _KEY_CACHE.pop(fp, None)
            return None
        # Absolute key expiry is enforced on every hit (audit A33): the
        # key's expires_at can fall inside the cache TTL window, and the
        # cache must never be more permissive than the DB check in
        # _resolve_key (``expires_at < utc_now()``).
        if expires_at is not None and expires_at < utc_now():
            _KEY_CACHE.pop(fp, None)
            return None
        return actor


def invalidate_key_cache(key_id: int | None = None) -> int:
    """Drop cached resolves for one API key (or all when ``key_id`` is
    None). Called by the api_keys CRUD on disable / delete / rotate so
    revocation is immediate instead of lagging up to
    ``_KEY_CACHE_TTL_SEC`` (audit 2026-11-07 H-4). Returns the number
    of entries removed."""
    from .core.ws_registry import get_ws_registry

    global _KEY_CACHE_GENERATION
    with _KEY_CACHE_LOCK:
        # Advance the generation so any verify already in flight (gen captured
        # before its DB read) is barred from filling the cache afterwards (F05).
        _KEY_CACHE_GENERATION += 1
        if key_id is None:
            n = len(_KEY_CACHE)
            _KEY_CACHE.clear()
            # Close every key-authenticated live stream too (audit A07).
            get_ws_registry().close_all_keys()
            return n
        victims = [fp for fp, (_, actor, _) in _KEY_CACHE.items() if actor.id == key_id]
        for fp in victims:
            _KEY_CACHE.pop(fp, None)
        # Immediately drop any live WS streams on this key (audit A07).
        get_ws_registry().close_key(key_id)
        return len(victims)


def _key_cache_set(
    raw: str, actor: Actor, expires_at: datetime | None = None, gen: int | None = None
) -> None:
    fp = _key_cache_fingerprint(raw)
    now = _time.monotonic()
    with _KEY_CACHE_LOCK:
        # F05: if a revocation advanced the generation after this verify
        # captured `gen` (before its DB read), do NOT cache — the key may
        # have just been disabled/deleted and must not be restored.
        if gen is not None and gen != _KEY_CACHE_GENERATION:
            return
        # Naive size cap: when we hit the ceiling, drop one expired
        # entry (or arbitrary one if none expired). For our scale
        # (<20 active keys) this almost never fires.
        if len(_KEY_CACHE) >= _KEY_CACHE_MAX:
            for k, (kts, _, _) in list(_KEY_CACHE.items()):
                if now - kts > _KEY_CACHE_TTL_SEC:
                    _KEY_CACHE.pop(k, None)
                    break
            else:
                _KEY_CACHE.pop(next(iter(_KEY_CACHE)), None)
        _KEY_CACHE[fp] = (now, actor, expires_at)


# ── Wrong-key budget (audit P07) ─────────────────────────────────────
# A wrong key that shares a real key's 8-character prefix costs one bcrypt
# (~250 ms of CPU) per key in that bucket, and the prefix is ``alertd_`` plus
# one character — 64 guesses. Unbounded, a few such requests per second from
# an unauthenticated client fill the hashing pool and stall every caller.
# Three bounds: a client IP gets a handful of wrong keys per minute, the
# hashing queue has a ceiling, and no DB connection is held while hashing.
_KEY_FAIL_WINDOW_SEC = 60.0
_KEY_FAIL_MAX = 5
_KEY_FAIL_IPS_MAX = 10_000
# Insertion-ordered by the last failure: the front is the address that failed
# longest ago, so making room costs O(1) (review K15 — a full rebuild of 10,000
# entries per new address blocked the loop ~3 ms a request).
_KEY_FAILURES: OrderedDict[str, list[float]] = OrderedDict()
# Verifications allowed to wait for a hashing slot, on top of those running.
_KEY_VERIFY_QUEUE_MAX = 16
_key_verifies_pending = 0


def _budget_key(ip: str) -> str:
    """The unit a budget is kept for: the address, or its /64 for IPv6 (a
    client gets a whole /64; one budget per /128 would be one per request)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def _key_failures_recent(key: str, now: float) -> list[float]:
    recent = [t for t in _KEY_FAILURES.get(key, ()) if now - t < _KEY_FAIL_WINDOW_SEC]
    if recent:
        _KEY_FAILURES[key] = recent
    else:
        _KEY_FAILURES.pop(key, None)
    return recent


def _key_failure_budget_spent(ip: str | None) -> bool:
    return bool(ip) and len(_key_failures_recent(_budget_key(cast(str, ip)), _time.monotonic())) >= _KEY_FAIL_MAX


def _note_key_failure(ip: str | None) -> None:
    if not ip:
        return
    key = _budget_key(ip)
    now = _time.monotonic()
    recent = _key_failures_recent(key, now)
    if key not in _KEY_FAILURES:
        while len(_KEY_FAILURES) >= _KEY_FAIL_IPS_MAX:
            _KEY_FAILURES.popitem(last=False)    # the address that failed longest ago
    _KEY_FAILURES[key] = [*recent, now]
    _KEY_FAILURES.move_to_end(key)


def _refund_key_failure(ip: str | None) -> None:
    """Take back the failure counted up front for a verification that did
    not turn out to be a wrong key (right key, expired key, busy)."""
    if not ip:
        return
    key = _budget_key(ip)
    stamps = _KEY_FAILURES.get(key)
    if stamps:
        stamps.pop()
        if not stamps:
            _KEY_FAILURES.pop(key, None)


def reset_key_failures() -> None:
    """Forget every wrong-key count (tests)."""
    global _key_verifies_pending
    _KEY_FAILURES.clear()
    _key_verifies_pending = 0


class _WrongSource(Exception):
    """A right key used from an address its allowlist does not include."""


def _key_networks(row: ApiKey) -> tuple[Network, ...]:
    # Stored normalised (schemas/api_key.py); parsing is cached per list.
    return parse_networks(tuple(row.allowed_cidrs or ()), label="address",
                          catch_all="allows every address; leave the list empty for that")


def _source_allowed(actor: Actor, client_ip: str | None) -> bool:
    """No allowlist, or the client address is in it. Without an address
    (no peer) a restricted key is refused."""
    if not actor.allowed_networks:
        return True
    return client_ip is not None and in_networks(client_ip, actor.allowed_networks)


def _source_refused() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="This API key is not allowed from this address")


# Each key's rate allowance (api_keys.rate_limit_per_min), by key id: kept
# across the resolve cache and edits of the key, so neither refills it.
_KEY_RATE = PerMinuteLimiter()


def reset_key_rates() -> None:
    """Forget every key's rate allowance (tests: key ids repeat per database)."""
    _KEY_RATE.forget()


def _admit(actor: Actor) -> None:
    """Spend one request of the key's own rate limit, or refuse it with 429
    and the seconds until the next one fits. The key is right, so this is
    not a wrong key for anybody's budget."""
    limit = actor.rate_limit_per_min
    if limit is None or actor.id is None:
        return
    admission = _KEY_RATE.admit(actor.id, limit)
    if admission.allowed:
        return
    from .metrics import API_KEY_RATE_LIMITED_TOTAL

    API_KEY_RATE_LIMITED_TOTAL.labels(key=actor.name).inc()
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"This API key is limited to {limit} requests a minute",
        headers={"Retry-After": str(max(1, math.ceil(admission.retry_after)))},
    )


async def _resolve_key(
    raw: str,
    session: AsyncSession,
    client_ip: str | None,
) -> Actor:
    """The actor of a plaintext API key, admitted within the key's rate
    limit — the one entry point for HTTP and WebSocket alike.

    Raises what ``_authenticate_key`` raises, and 429 (with ``Retry-After``)
    for a right key over its ``rate_limit_per_min``.
    """
    actor = await _authenticate_key(raw, session, client_ip)
    _admit(actor)
    return actor


async def _authenticate_key(
    raw: str,
    session: AsyncSession,
    client_ip: str | None,
) -> Actor:
    """Verify a plaintext API key against the DB.

    Returns the Actor on success; raises 401/403 otherwise — 429 once
    ``client_ip`` has spent its wrong-key budget, 503 when too many
    verifications are already waiting for a hashing slot.

    Caches successful resolves for ``_KEY_CACHE_TTL_SEC`` seconds
    (audit M-7) to avoid bcrypt-checking every request.

    A key restricted to some addresses (``allowed_cidrs``) used from another
    one gets ``403`` — after the key is known to be right, before its use is
    recorded — and counts once as a wrong key for that address, on every
    path: cache hit, digest and bcrypt.
    """
    global _key_verifies_pending
    if not raw or len(raw) < 16:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid API key format")

    # Fast path — cache hit
    cached = _key_cache_get(raw)
    if cached is not None:
        if not _source_allowed(cached, client_ip):
            _note_key_failure(client_ip)
            raise _source_refused()
        return cached

    # Capture the revocation generation BEFORE reading the key, so a
    # disable/delete that commits while we verify bars the cache fill
    # below (audit F05).
    gen0 = _key_cache_generation()

    # Digest path: a generated key is found by the SHA-256 of its text — one
    # indexed read, no bcrypt. A wrong key costs nothing more than that, and a
    # right one never waits behind wrong ones in the hashing queue.
    digest = key_digest(raw)
    if digest is not None:
        row = (
            await session.execute(select(ApiKey).where(ApiKey.key_digest == digest, ApiKey.enabled == true()))
        ).scalar_one_or_none()
        if row is not None:
            try:
                return await _accept_key(session, row, raw, client_ip, gen0)
            except _WrongSource:
                _note_key_failure(client_ip)
                raise _source_refused() from None

    # bcrypt path: keys issued before the digest column existed (their digest
    # is written below, on first use) and keys chosen by the operator.
    if _key_failure_budget_spent(client_ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many invalid API keys from this address",
            headers={"Retry-After": str(int(_KEY_FAIL_WINDOW_SEC))},
        )
    # Count this attempt as a failure NOW, before any await, and refund it if
    # it turns out not to be one (review K15): checked here but recorded after
    # hashing, a burst of concurrent wrong keys all passed the check above.
    _note_key_failure(client_ip)
    wrong = False
    try:
        rows = (
            await session.execute(
                select(ApiKey).where(
                    ApiKey.key_prefix == raw[:8], ApiKey.enabled == true(), ApiKey.key_digest.is_(None))
            )
        ).scalars().all()
        # End the read transaction: the pooled connection goes back before the
        # (slow, queued) hashing, so wrong keys cannot drain the pool.
        await session.commit()

        for row in rows:
            if _key_verifies_pending >= get_settings().hash_max_concurrency + _KEY_VERIFY_QUEUE_MAX:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is busy, retry shortly",
                    headers={"Retry-After": "1"},
                )
            _key_verifies_pending += 1
            try:
                matches = await _checkpw_async(raw.encode("utf-8"), row.key_hash.encode("utf-8"))
            except ValueError:
                # Malformed bcrypt hash in DB — skip the row
                continue
            finally:
                _key_verifies_pending -= 1
            if matches:
                try:
                    return await _accept_key(session, row, raw, client_ip, gen0, store_digest=digest)
                except _WrongSource:
                    wrong = True        # keep the failure reserved above: counted once
                    raise _source_refused() from None

        wrong = True
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    finally:
        if not wrong:
            _refund_key_failure(client_ip)


async def _accept_key(
    session: AsyncSession, row: ApiKey, raw: str, client_ip: str | None, gen0: int,
    *, store_digest: str | None = None,
) -> Actor:
    """The key is right: enforce its expiry and source allowlist, stamp its
    use, cache the actor. Raises ``_WrongSource`` for a refused address
    (the caller counts it), before anything is recorded."""
    if row.expires_at is not None and row.expires_at < utc_now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="API key expired")
    actor = Actor(kind="api_key", id=row.id, name=row.name, scopes=frozenset(row.scopes or []),
                  allowed_networks=_key_networks(row), rate_limit_per_min=row.rate_limit_per_min)
    if not _source_allowed(actor, client_ip):
        raise _WrongSource
    # Best-effort, no commit barrier. On cached hits we skip this —
    # last_used_at lags by up to _KEY_CACHE_TTL_SEC. Acceptable for audit use.
    values: dict[str, object] = {"last_used_at": utc_now(), "last_used_ip": client_ip}
    if store_digest is not None:
        values["key_digest"] = store_digest
    await session.execute(update(ApiKey).where(ApiKey.id == row.id).values(**values))
    _key_cache_set(raw, actor, row.expires_at, gen=gen0)
    return actor


# ── Browser sessions (admin UI, migration 0008) ───────────────────

SESSION_COOKIE = "alertd_session"
CSRF_COOKIE = "alertd_csrf"
CSRF_HEADER = "X-CSRF-Token"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# The only cookie-authenticated writes allowed while must_change_password=1.
_PASSWORD_CHANGE_ALLOWED_PATHS = frozenset({"/v1/auth/password", "/v1/auth/logout"})

# A valid HTTP authority is host[:port], optionally bracketed for IPv6. We
# reject anything with other characters (``/``, ``@``, whitespace, …) so a
# crafted Host can't confuse Origin comparison or URL reconstruction (A-02).
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-:\[\]]+$")


@dataclass
class SessionContext:
    """Per-request facts about the resolved browser session."""

    session_id: int
    user_id: int
    username: str
    csrf_token: str
    must_change_password: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


def session_token_hash(raw: str) -> str:
    """sha256 hex of the cookie token — what ``admin_sessions`` stores."""
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()


def session_expiry(created_at: datetime, last_seen_at: datetime) -> datetime:
    """min(created + SESSION_MAX_DAYS, last_seen + SESSION_IDLE_HOURS)."""
    s = get_settings()
    return min(
        created_at + timedelta(days=s.session_max_days),
        last_seen_at + timedelta(hours=s.session_idle_hours),
    )


# Same 30 s cache idea as API keys: the DB row is re-read (and touched)
# at most every _KEY_CACHE_TTL_SEC per session. Keyed by token hash.
_SESSION_CACHE: dict[str, tuple[float, Actor, SessionContext]] = {}

# Monotonic revocation generation (audit A-11), mirroring the API-key guard.
# Bumped on every logout / revoke / password-change. A cold session lookup
# captures the generation before its DB read; if a revocation advances it
# before the fill, the fill is skipped so an in-flight lookup can't restore a
# just-revoked session for the rest of the TTL. Guarded by _KEY_CACHE_LOCK.
_SESSION_CACHE_GENERATION = 0


def _session_cache_generation() -> int:
    with _KEY_CACHE_LOCK:
        return _SESSION_CACHE_GENERATION


def invalidate_session_cache(
    *, session_id: int | None = None, user_id: int | None = None
) -> int:
    """Drop cached sessions — one, all of a user's, or all. Called on
    logout / revoke / password change so the effect is immediate."""
    from .core.ws_registry import get_ws_registry

    global _SESSION_CACHE_GENERATION
    reg = get_ws_registry()
    with _KEY_CACHE_LOCK:
        # Advance the generation so any session resolve already in flight (gen
        # captured before this revocation) won't restore the dropped entry (A-11).
        _SESSION_CACHE_GENERATION += 1
        if session_id is None and user_id is None:
            n = len(_SESSION_CACHE)
            _SESSION_CACHE.clear()
            # Close every session-authenticated live stream too (A07).
            reg.close_all_sessions()
            return n
        victims = [
            fp for fp, (_, _, ctx) in _SESSION_CACHE.items()
            if (session_id is not None and ctx.session_id == session_id)
            or (user_id is not None and ctx.user_id == user_id)
        ]
        for fp in victims:
            _SESSION_CACHE.pop(fp, None)
        # Immediately drop any live WS streams for this session / user
        # (audit A07: logout / revoke / password-change must land now).
        if session_id is not None:
            reg.close_session(session_id)
        if user_id is not None:
            reg.close_user(user_id)
        return len(victims)


def _session_cache_get(fp: str) -> tuple[Actor, SessionContext] | None:
    now = _time.monotonic()
    with _KEY_CACHE_LOCK:
        entry = _SESSION_CACHE.get(fp)
        if entry is None:
            return None
        ts, actor, ctx = entry
        if now - ts > _KEY_CACHE_TTL_SEC:
            _SESSION_CACHE.pop(fp, None)
            return None
    # Absolute expiry is enforced even on cache hits.
    if ctx.expires_at <= utc_now():
        invalidate_session_cache(session_id=ctx.session_id)
        return None
    return actor, ctx


def _session_cache_set(
    fp: str, actor: Actor, ctx: SessionContext, gen: int | None = None
) -> None:
    with _KEY_CACHE_LOCK:
        # A-11: if a revocation advanced the generation after this lookup
        # captured `gen` (i.e. the session was logged out / revoked / its
        # password changed while we were reading the DB), skip the fill so a
        # just-revoked session isn't restored for the cache TTL.
        if gen is not None and gen != _SESSION_CACHE_GENERATION:
            return
        if len(_SESSION_CACHE) >= _KEY_CACHE_MAX:
            _SESSION_CACHE.pop(next(iter(_SESSION_CACHE)), None)
        _SESSION_CACHE[fp] = (_time.monotonic(), actor, ctx)


def _session_401(reason: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail={"code": "SESSION_INVALID", "message": reason},
        headers={"WWW-Authenticate": "Cookie"},
    )


async def _resolve_session(raw: str, session: AsyncSession) -> tuple[Actor, SessionContext]:
    """Validate a cookie token against ``admin_sessions`` and touch it.

    Raises 401 on unknown / revoked / expired session or inactive user.
    """
    if not raw or len(raw) < 16:
        raise _session_401("Invalid session")
    fp = session_token_hash(raw)
    cached = _session_cache_get(fp)
    if cached is not None:
        return cached

    # Capture the revocation generation before the DB read so a concurrent
    # logout/revoke during the read skips our later cache fill (A-11).
    gen = _session_cache_generation()
    row = (
        await session.execute(
            select(AdminSession, AdminUser)
            .join(AdminUser, AdminUser.id == AdminSession.user_id)
            .where(AdminSession.token_hash == fp)
        )
    ).first()
    if row is None:
        raise _session_401("Invalid session")
    sess, user = row
    now = utc_now()
    if sess.revoked_at is not None:
        raise _session_401("Session revoked")
    if sess.expires_at <= now:
        raise _session_401("Session expired")
    if not user.is_active:
        raise _session_401("Account disabled")

    # Touch: slide the idle window (bounded by the absolute lifetime).
    sess.last_seen_at = now
    sess.expires_at = session_expiry(sess.created_at, now)

    actor = Actor(
        kind="user",
        id=user.id,
        name=user.username,
        scopes=frozenset({"admin"}),
        session_id=sess.id,
    )
    ctx = SessionContext(
        session_id=sess.id,
        user_id=user.id,
        username=user.username,
        csrf_token=sess.csrf_token,
        must_change_password=bool(user.must_change_password),
        created_at=sess.created_at,
        last_seen_at=sess.last_seen_at,
        expires_at=sess.expires_at,
    )
    _session_cache_set(fp, actor, ctx, gen)
    return actor, ctx


def _enforce_browser_write_rules(request: Request, ctx: SessionContext) -> None:
    """CSRF + must-change-password gate for cookie-authenticated writes.

    Defence in depth on top of ``SameSite=Strict``:
    - ``Sec-Fetch-Site``, when the browser sends it, must be
      ``same-origin`` or ``none`` (direct navigation);
    - ``Origin``, when present, must match the request ``Host``;
    - ``X-CSRF-Token`` must equal the session's csrf token
      (double-submit — the SPA reads it from the ``alertd_csrf`` cookie).
    API-key callers never reach this function (no cookie → no CSRF).
    """
    if request.method in _SAFE_METHODS:
        return

    def _csrf_403(msg: str) -> HTTPException:
        return HTTPException(
            status.HTTP_403_FORBIDDEN, detail={"code": "CSRF_FAILED", "message": msg}
        )

    # Reject a malformed Host up front: it feeds the Origin comparison below
    # and any URL reconstruction, and a crafted authority is the lever in the
    # A-02 bypass. A well-behaved client always sends a clean Host.
    host = request.headers.get("host", "")
    if host and not _HOST_RE.match(host):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_HOST", "message": "Malformed Host header"},
        )

    sfs = request.headers.get("sec-fetch-site")
    if sfs and sfs not in ("same-origin", "none"):
        raise _csrf_403(f"Cross-site request refused (Sec-Fetch-Site={sfs})")
    origin = request.headers.get("origin")
    if origin:
        if urlsplit(origin).netloc.lower() != host.lower():
            raise _csrf_403("Origin does not match host")
    token = request.headers.get(CSRF_HEADER)
    if not token or not hmac.compare_digest(token, ctx.csrf_token):
        raise _csrf_403(f"Missing or invalid {CSRF_HEADER} header")

    # Decide on the routed ASGI path, never request.url.path: the latter is
    # reconstructed from the Host header, so a crafted Host can make it read as
    # an allowed path while the request is actually routed to a config-write
    # endpoint, bypassing this gate. scope["path"] is what the router matched.
    routed_path = request.scope.get("path", "")
    if ctx.must_change_password and routed_path not in _PASSWORD_CHANGE_ALLOWED_PATHS:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PASSWORD_CHANGE_REQUIRED",
                "message": "Change the account password before making changes",
            },
        )


async def get_current_actor(
    request: Request,
    api_key: str | None = Depends(_HEADER),
    session: AsyncSession = Depends(get_session),
) -> Actor:
    """FastAPI dependency: resolve the actor from the API-key header or,
    failing that, the browser session cookie.

    Use this directly when scope check is per-handler; use
    ``require_scope`` factory when scope is endpoint-uniform.
    """
    # The caller's address as the login guard sees it: behind a trusted proxy
    # the TCP peer is the proxy, and one budget for everybody behind it would
    # let one client lock the others out.
    client_ip = real_client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"), get_settings().trusted_proxy_cidr_list,
    )
    if api_key:
        actor = await _resolve_key(api_key, session, client_ip)
        request.state.actor = actor
        return actor

    raw_cookie = request.cookies.get(SESSION_COOKIE)
    if raw_cookie:
        actor, ctx = await _resolve_session(raw_cookie, session)
        _enforce_browser_write_rules(request, ctx)
        request.state.actor = actor
        request.state.session_ctx = ctx
        return actor

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Missing X-API-Key header",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_user_session(actor: Actor = Depends(get_current_actor)) -> Actor:
    """Dependency for endpoints that only make sense for a human session
    (logout, password change, session management). An API key — even
    an admin one — is refused: machines must not change people's
    passwords."""
    if not actor.is_user:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "SESSION_REQUIRED",
                "message": "This endpoint requires a browser session, not an API key",
            },
        )
    return actor


def require_scope(scope: str):
    """Dependency factory: ``Depends(require_scope("admin"))``."""

    async def _dep(actor: Actor = Depends(get_current_actor)) -> Actor:
        if not actor.has_scope(scope):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {scope}",
            )
        return actor

    _dep.__name__ = f"require_scope_{scope}"
    return _dep


# ── Bcrypt helpers (also used by api_keys CRUD + bootstrap) ────────


def hash_key(plaintext: str) -> str:
    """Return bcrypt hash. Cost=12 → ~250 ms on a modern CPU."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


async def hash_key_async(plaintext: str) -> str:
    """``hash_key`` offloaded to the bounded crypto pool (audit A13)."""
    from .core.crypto_pool import run_in_pool
    return await run_in_pool(hash_key, plaintext)


async def _checkpw_async(raw: bytes, hashed: bytes) -> bool:
    """bcrypt.checkpw offloaded to the bounded crypto pool (audit A13) so
    per-request key verification doesn't block the event loop."""
    from .core.crypto_pool import run_in_pool
    return await run_in_pool(bcrypt.checkpw, raw, hashed)


# ``alertd_`` + secrets.token_urlsafe(32): 43 URL-safe characters, 256 random bits.
_GENERATED_KEY_RE = re.compile(r"^alertd_[A-Za-z0-9_-]{43}$")


def key_digest(plaintext: str) -> str | None:
    """SHA-256 of a *generated* key, for the indexed lookup; None for any other.

    A fast hash is enough for 256 random bits and lets a key be found without
    bcrypt. A key the operator chose (``ALERTD_BOOTSTRAP_ADMIN_KEY``) may be
    weak, and a fast hash of a weak secret is cheap to reverse from a leaked
    table — such a key keeps bcrypt only.
    """
    if not _GENERATED_KEY_RE.fullmatch(plaintext):
        return None
    return _hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_key_plaintext() -> str:
    """Generate a fresh API key. Format: ``alertd_<43-url-safe-chars>``."""
    import secrets

    return "alertd_" + secrets.token_urlsafe(32)
