"""``/v1/state`` and ``/v1/stream/state`` — debug visibility into
the live state cache.

``GET /v1/state`` is paged-by-no-paging (current size is small);
clients render it in the admin UI's "State" tab.

``WS /v1/stream/state`` broadcasts every value update. Useful for
live debugging — admin watches the firehose to verify a topic is
flowing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.security.api_key import APIKeyQuery

from ...auth import (
    SESSION_COOKIE,
    Actor,
    _resolve_key,
    _resolve_session,
    client_address,
    require_scope,
    scope_grants,
)
from ...core.manager import get_manager
from ...core.state_cache import VarSnapshot
from ...core.ws_registry import StreamLimitReached, get_ws_registry
from ...db import get_session
from ...schemas.variable import StateResponse, VarState
from ...utils.time import utc_now

logger = logging.getLogger(__name__)
router = APIRouter()

# A live stream re-checks its auth this often (audit A07): the registry
# closes a session/key the instant it is revoked, but idle *expiry*
# fires no event, so each stream also re-validates on this cadence.
_REVALIDATE_SEC = 30


def _register_stream(websocket: WebSocket, actor: Actor) -> int:
    """Track this open stream by its auth identity so a revoke can close
    it immediately (audit A07). Raises ``StreamLimitReached`` when the
    caller (or the process) holds the most streams allowed (review F14)."""
    reg = get_ws_registry()
    if actor.kind == "user":
        return reg.register(websocket, session_id=actor.session_id, user_id=actor.id)
    if actor.kind == "api_key":
        return reg.register(websocket, key_id=actor.id)
    return reg.register(websocket)


async def _accept_registered(websocket: WebSocket, actor: Actor) -> int | None:
    """Reserve the stream's place, then accept it: the registry handle, or
    ``None`` after closing a stream there is no room for (1013, try again
    later — before it is accepted, so it is never served)."""
    try:
        handle = _register_stream(websocket, actor)
    except StreamLimitReached as e:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason=str(e)[:120])
        return None
    try:
        await websocket.accept()
    except BaseException:
        get_ws_registry().unregister(handle)       # the place is not held by a stream that never opened
        raise
    return handle


async def _still_valid(actor: Actor) -> bool:
    """Re-resolve the stream's session/key against the DB — False once it
    is revoked, expired, disabled, or the user is deactivated."""
    from ...db.models import AdminSession, AdminUser, ApiKey

    async for session in get_session():
        if actor.kind == "user":
            if actor.session_id is None:
                return False
            sess = await session.get(AdminSession, actor.session_id)
            if sess is None or sess.revoked_at is not None or sess.expires_at <= utc_now():
                return False
            user = await session.get(AdminUser, actor.id)
            return user is not None and user.is_active
        if actor.kind == "api_key":
            key = await session.get(ApiKey, actor.id)
            if key is None or not key.enabled:
                return False
            if key.expires_at is not None and key.expires_at < utc_now():
                return False
            # Enforce the *current* read scope too — a key whose scopes were
            # reduced to drop `read` must lose its live stream (audit F06).
            # Use the shared scope hierarchy so an admin-only key (which implies
            # `read`) is not wrongly dropped mid-stream (audit A-13).
            if not scope_grants(key.scopes or [], "read"):
                return False
            return True
        return True  # system / jwt — no revocation model
    return False  # pragma: no cover - get_session always yields


async def _close_revoked(websocket: WebSocket) -> None:
    try:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="session expired or revoked",
        )
    except Exception:  # pragma: no cover - already closing
        pass


@router.get("/state", response_model=StateResponse, summary="Live state cache snapshot")
async def get_state(
    actor: Actor = Depends(require_scope("read")),
) -> StateResponse:
    """Return current values for all known variables.

    Excludes variables that have not received their first value yet
    (they don't appear in the cache).
    """
    cache = get_manager().cache
    snap = cache.snapshot()
    import time as _time

    now = _time.monotonic()
    items = [
        VarState(
            name=name,
            value=s.value,
            age_sec=round(s.age_sec(now), 3),
            wall_ts=s.wall_ts,
            source_topic=s.source_topic,
            source_kind=s.source_kind,
        )
        for name, s in sorted(snap.items())
    ]
    return StateResponse(
        variables=items,
        cache_size=len(snap),
        last_mqtt_ts=cache.last_mqtt_ts(),
    )


# ── WebSocket stream ──────────────────────────────────────────────


_ws_apikey = APIKeyQuery(name="api_key", auto_error=False)


async def _ws_authenticate(websocket: WebSocket) -> Actor | None:
    """Resolve the caller of a WebSocket handshake, or close it.

    Order mirrors ``get_current_actor``: ``?api_key=`` query param
    (machines — browsers cannot set headers on a WS), then the
    ``alertd_session`` cookie (admin UI, same origin). For the cookie
    path the ``Origin`` header, when the browser sends it, must match
    ``Host`` — WebSockets ignore SameSite, so this is the CSRF check.
    Requires ``read`` scope. Returns None after closing on failure.
    """
    api_key = websocket.query_params.get("api_key")
    cookie = websocket.cookies.get(SESSION_COOKIE)
    if not api_key and not cookie:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                              reason="Missing api_key query param or session cookie")
        return None

    if not api_key:
        origin = websocket.headers.get("origin")
        host = websocket.headers.get("host", "")
        if origin and urlsplit(origin).netloc.lower() != host.lower():
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                                  reason="Origin does not match host")
            return None

    async for session in get_session():
        try:
            if api_key:
                actor = await _resolve_key(api_key, session, client_address(websocket))
            else:
                actor, _ctx = await _resolve_session(cookie or "", session)
        except Exception as e:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                                  reason=f"Auth failed: {type(e).__name__}")
            return None
        if not actor.has_scope("read"):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                                  reason="Missing scope: read")
            return None
        return actor
    return None  # pragma: no cover


@router.websocket("/stream/notifications")
async def stream_notifications(websocket: WebSocket) -> None:
    """Live feed of notifications dispatched to the ``ui`` channel.

    Auth: ``?api_key=...`` query param or the ``alertd_session`` cookie
    (same-origin admin UI). Requires ``read`` scope.

    Frame format::

        {"type":"notification", "id":"...", "notification_type":"...",
         "severity":"warning", "icon":"⚠️", "title":"...", "message":"...",
         "fired_at":"2026-...", "rule_id":N}

    Plus ``{"type":"hello"}`` greeting on connect.
    """
    actor = await _ws_authenticate(websocket)
    if actor is None:
        return
    reg = get_ws_registry()
    reg_handle = await _accept_registered(websocket, actor)
    if reg_handle is None:
        return

    from ...channels.ui import get_broadcaster

    broadcaster = get_broadcaster()
    handle: int | None = None
    # From the reservation on, everything is released however the stream
    # ends — a failed greeting included — so a place is never held by a
    # stream that is gone (MAX_PER_IDENTITY would lock the caller out).
    try:
        await websocket.send_text(json.dumps({"type": "hello"}))
        handle = await broadcaster.register(websocket)
        # Close the handshake/registration race (A-11): a revoke that committed
        # between authentication and registration would have found no stream to
        # close, so re-check against the DB now that we are registered.
        if not await _still_valid(actor):
            await _close_revoked(websocket)
            return
        # Block until disconnect — the broadcaster pumps for us. Re-validate
        # auth on an ABSOLUTE deadline, not only on an idle timeout: a client
        # that sends frames more often than _REVALIDATE_SEC would otherwise
        # never time out and never revalidate, evading passive expiry (F06).
        next_check = time.monotonic() + _REVALIDATE_SEC
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=_REVALIDATE_SEC)
            except TimeoutError:
                pass
            except WebSocketDisconnect:
                break
            if time.monotonic() >= next_check:
                if not await _still_valid(actor):
                    await _close_revoked(websocket)
                    break
                next_check = time.monotonic() + _REVALIDATE_SEC
    finally:
        reg.unregister(reg_handle)
        if handle is not None:
            await broadcaster.unregister(handle)


@router.websocket("/stream/state")
async def stream_state(websocket: WebSocket) -> None:
    """Broadcast every state cache update.

    Auth: ``?api_key=...`` query param or the ``alertd_session`` cookie
    (browsers cannot set custom WS headers). Requires ``read`` scope.

    Frame format::

        {"type":"update", "name":"...", "value":..., "wall_ts":...,
         "source_topic":"...", "source_kind":"mqtt"}

    Plus a ``{"type":"hello", "cache_size":N}`` greeting on connect.
    """
    actor = await _ws_authenticate(websocket)
    if actor is None:
        return
    reg = get_ws_registry()
    reg_handle = await _accept_registered(websocket, actor)
    if reg_handle is None:
        return
    cache = get_manager().cache
    queue: asyncio.Queue[tuple[str, VarSnapshot]] = asyncio.Queue(maxsize=100)

    async def _on_update(name: str, snap: VarSnapshot) -> None:
        try:
            queue.put_nowait((name, snap))
        except asyncio.QueueFull:
            # Client too slow — drop oldest, keep newest
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait((name, snap))
            except asyncio.QueueFull:
                pass

    cancel: Callable[[], None] | None = None
    # From the reservation on, everything is released however the stream ends.
    try:
        await websocket.send_text(json.dumps({"type": "hello", "cache_size": len(cache.snapshot())}))
        cancel = cache.subscribe(_on_update)
        # Close the handshake/registration race (A-11): re-check validity now
        # that we are registered, in case a revoke committed before registration.
        if not await _still_valid(actor):
            await _close_revoked(websocket)
            return
        # Absolute revalidation deadline (F06): a continuously-updating stream
        # never hits the idle timeout, so check the clock on every wakeup.
        next_check = time.monotonic() + _REVALIDATE_SEC
        while True:
            got: tuple[str, VarSnapshot] | None = None
            try:
                got = await asyncio.wait_for(queue.get(), timeout=_REVALIDATE_SEC)
            except TimeoutError:
                pass
            if time.monotonic() >= next_check:
                if not await _still_valid(actor):
                    await _close_revoked(websocket)
                    break
                next_check = time.monotonic() + _REVALIDATE_SEC
            if got is None:
                continue
            name, snap = got
            try:
                await websocket.send_text(json.dumps({
                    "type": "update",
                    "name": name,
                    "value": snap.value,
                    "wall_ts": snap.wall_ts,
                    "source_topic": snap.source_topic,
                    "source_kind": snap.source_kind,
                }, default=str))
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        reg.unregister(reg_handle)
        if cancel is not None:
            cancel()
        try:
            await websocket.close()
        except Exception:
            pass
