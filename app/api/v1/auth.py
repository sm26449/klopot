"""``/v1/auth`` — browser login for the admin UI.

Opaque sessions: the
cookie holds a random 256-bit token, the DB holds its sha256. No
signing key exists, so there is nothing to rotate or leak.

Every outcome is audited (``auth.*`` actions). Login failures are
deliberately uninformative (same 401 for unknown user / wrong
password / disabled account) and cost one argon2 verification in
every branch.
"""
from __future__ import annotations

import hashlib
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import record_change
from ...auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Actor,
    SessionContext,
    invalidate_session_cache,
    require_user_session,
    session_expiry,
    session_token_hash,
)
from ...config import get_settings
from ...core import login_guard, passwords
from ...core.crypto_pool import CryptoPoolBusy
from ...db import get_session
from ...db.models import AdminSession, AdminUser
from ...schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordChangeRequest,
    SessionRead,
    SessionsRevoked,
    UserRead,
)
from ...utils.client_ip import real_client_ip
from ...utils.time import utc_now

logger = logging.getLogger(__name__)
router = APIRouter()

_SYSTEM = Actor(kind="system", id=None, name="auth", scopes=frozenset())
def _audited_username(typed: str, account_exists: bool) -> str:
    """What the audit log (``read`` scope) may say about a failed sign-in's
    username (review K23): the name of an existing account, or a short digest —
    what was typed may be a password typed into the wrong field."""
    if account_exists:
        return typed
    return "unknown:" + hashlib.sha256(typed.encode("utf-8")).hexdigest()[:12]


# Sign-ins allowed to wait for a hashing slot on top of those running
# (review K07); beyond that the answer is 503, like wrong API keys (P07).
_LOGIN_VERIFY_QUEUE_MAX = 16


def _client_ip(request: Request) -> str | None:
    # Honor X-Forwarded-For from a trusted proxy so the per-IP login lockout
    # keys on the real client, not the reverse proxy (audit S-07).
    peer = request.client.host if request.client else None
    xff = request.headers.get("x-forwarded-for")
    return real_client_ip(peer, xff, get_settings().trusted_proxy_cidr_list)


def _user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    return ua[:255] if ua else None


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    common = {
        "secure": s.cookie_secure,
        "samesite": "strict",
        "path": "/",
        "max_age": s.session_max_days * 86400,
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)
    # Readable by the SPA (double-submit); carries no authority by itself.
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)


def _clear_session_cookies(response: Response) -> None:
    s = get_settings()
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=s.cookie_secure, samesite="strict")


def _ctx(request: Request) -> SessionContext:
    ctx = getattr(request.state, "session_ctx", None)
    if ctx is None:  # pragma: no cover — require_user_session guarantees it
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No session context")
    return ctx


async def _load_user(session: AsyncSession, user_id: int) -> AdminUser:
    user = await session.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Account no longer exists")
    return user


# ── Login / logout ────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in (sets the session cookies)",
    description=(
        "Browser login for the admin UI. On success sets the HttpOnly "
        "`alertd_session` cookie and the JS-readable `alertd_csrf` cookie; "
        "state-changing requests authenticated by cookie must then carry "
        "`X-CSRF-Token`. 401 on bad credentials (never says which part was "
        "wrong), 423 while the username or source IP is locked out, 503 "
        "(with `Retry-After`) while too many sign-ins wait for password hashing."
    ),
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    s = get_settings()
    ip = _client_ip(request)
    username = body.username.strip()

    lock = await login_guard.check(
        session,
        username=username,
        ip=ip,
        window_min=s.login_lockout_min,
        max_user=s.login_max_failures,
        max_ip=s.login_max_failures_per_ip,
    )
    if lock.locked:
        known = (await session.execute(
            select(AdminUser.id).where(AdminUser.username == username))).scalar_one_or_none() is not None
        await record_change(
            session, _SYSTEM, "auth.login_blocked",
            resource_kind="admin_user", resource_id=_audited_username(username, known),
            after={"ip": ip, "reason": lock.reason, "retry_after_sec": lock.retry_after_sec},
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_423_LOCKED,
            detail={
                "code": "LOCKED_OUT",
                "message": "Too many failed attempts; try again later",
                "retry_after_sec": lock.retry_after_sec,
            },
            headers={"Retry-After": str(lock.retry_after_sec)},
        )

    user = (
        await session.execute(select(AdminUser).where(AdminUser.username == username))
    ).scalar_one_or_none()
    # End the read transaction before hashing (review K07): the pooled
    # connection goes back while this request waits for an argon2 slot, so a
    # burst of anonymous logins cannot drain the pool the engine and the
    # delivery worker need. expire_on_commit=False keeps ``user`` loaded.
    await session.commit()
    # Verify even when the user is unknown/disabled (constant cost).
    try:
        ok = await passwords.verify_password_async(
            user.password_hash if user else None, body.password, queue_max=_LOGIN_VERIFY_QUEUE_MAX,
        )
    except CryptoPoolBusy:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "BUSY", "message": "Too many sign-ins at once, retry shortly"},
            headers={"Retry-After": "1"},
        ) from None
    if not user or not user.is_active or not ok:
        await login_guard.record(session, username=username, ip=ip, success=False)
        await record_change(
            session, _SYSTEM, "auth.login_failed",
            resource_kind="admin_user", resource_id=_audited_username(username, user is not None),
            after={"ip": ip, "user_agent": _user_agent(request)},
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"},
        )

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = await passwords.hash_password_async(body.password)

    now = utc_now()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    sess = AdminSession(
        user_id=user.id,
        token_hash=session_token_hash(token),
        csrf_token=csrf,
        created_at=now,
        last_seen_at=now,
        expires_at=session_expiry(now, now),
        ip=ip,
        user_agent=_user_agent(request),
    )
    session.add(sess)
    user.last_login_at = now
    user.last_login_ip = ip
    await login_guard.record(session, username=username, ip=ip, success=True)
    await session.flush()

    actor = Actor(
        kind="user", id=user.id, name=user.username,
        scopes=frozenset({"admin"}), session_id=sess.id,
    )
    await record_change(
        session, actor, "auth.login_ok",
        resource_kind="admin_session", resource_id=str(sess.id),
        after={"ip": ip, "user_agent": sess.user_agent, "expires_at": sess.expires_at},
    )
    await session.commit()

    _set_session_cookies(response, token, csrf)
    return LoginResponse(user=UserRead.model_validate(user), csrf_token=csrf)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out (revokes this session, clears cookies)",
)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_user_session),
) -> Response:
    ctx = _ctx(request)
    sess = await session.get(AdminSession, ctx.session_id)
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = utc_now()
    await record_change(
        session, actor, "auth.logout",
        resource_kind="admin_session", resource_id=str(ctx.session_id),
    )
    await session.commit()
    invalidate_session_cache(session_id=ctx.session_id)
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


# ── Me / password / sessions ──────────────────────────────────────


@router.get("/me", response_model=MeResponse, summary="Current user + session")
async def me(
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_user_session),
) -> MeResponse:
    ctx = _ctx(request)
    user = await _load_user(session, ctx.user_id)
    sess = await session.get(AdminSession, ctx.session_id)
    return MeResponse(
        user=UserRead.model_validate(user),
        scopes=sorted(actor.scopes),
        session=SessionRead.model_validate(sess, from_attributes=True).model_copy(
            update={"current": True}
        ),
    )


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password (revokes every other session)",
)
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_user_session),
) -> Response:
    ctx = _ctx(request)
    user = await _load_user(session, ctx.user_id)

    if not await passwords.verify_password_async(user.password_hash, body.current_password):
        await record_change(
            session, actor, "auth.password_change_failed",
            resource_kind="admin_user", resource_id=user.username,
            after={"reason": "current password mismatch"},
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect"},
        )

    problems = passwords.validate_password_policy(
        body.new_password, username=user.username, current_password=body.current_password
    )
    if problems:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "PASSWORD_POLICY", "message": "; ".join(problems), "problems": problems},
        )

    now = utc_now()
    user.password_hash = await passwords.hash_password_async(body.new_password)
    user.must_change_password = False
    user.password_changed_at = now

    others = (
        await session.execute(
            select(AdminSession).where(
                AdminSession.user_id == user.id,
                AdminSession.id != ctx.session_id,
                AdminSession.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    for s in others:
        s.revoked_at = now

    await record_change(
        session, actor, "auth.password_changed",
        resource_kind="admin_user", resource_id=user.username,
        after={"other_sessions_revoked": len(others)},
    )
    await session.commit()
    # Drop every cached session of this user so the current one is
    # re-read (must_change_password=0) and the others die now.
    invalidate_session_cache(user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionRead], summary="List own active sessions")
async def list_sessions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_user_session),
) -> list[SessionRead]:
    ctx = _ctx(request)
    rows = (
        await session.execute(
            select(AdminSession)
            .where(
                AdminSession.user_id == ctx.user_id,
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > utc_now(),
            )
            .order_by(AdminSession.last_seen_at.desc())
        )
    ).scalars().all()
    return [
        SessionRead.model_validate(r).model_copy(update={"current": r.id == ctx.session_id})
        for r in rows
    ]


@router.delete(
    "/sessions",
    response_model=SessionsRevoked,
    summary="Revoke all other sessions of the current user",
)
async def revoke_other_sessions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_user_session),
) -> SessionsRevoked:
    ctx = _ctx(request)
    now = utc_now()
    rows = (
        await session.execute(
            select(AdminSession).where(
                AdminSession.user_id == ctx.user_id,
                AdminSession.id != ctx.session_id,
                AdminSession.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    for r in rows:
        r.revoked_at = now
    await record_change(
        session, actor, "auth.sessions_revoked_others",
        resource_kind="admin_user", resource_id=actor.name,
        after={"revoked": len(rows), "ids": [r.id for r in rows]},
    )
    await session.commit()
    for r in rows:
        invalidate_session_cache(session_id=r.id)
    return SessionsRevoked(revoked=len(rows))


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke one of own sessions",
)
async def revoke_session(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_user_session),
) -> Response:
    ctx = _ctx(request)
    row = await session.get(AdminSession, session_id)
    if row is None or row.user_id != ctx.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    if row.revoked_at is None:
        row.revoked_at = utc_now()
    await record_change(
        session, actor, "auth.session_revoked",
        resource_kind="admin_session", resource_id=str(session_id),
        after={"current": session_id == ctx.session_id},
    )
    await session.commit()
    invalidate_session_cache(session_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
