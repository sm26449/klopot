"""Regression tests for audit A07 — a WebSocket stream stayed authorized
after logout / revoke / expiry because auth happened only at handshake.

Full-handshake E2E lives in the Playwright smoke (``wsAfterLogout``); here
we cover the mechanism directly: the connection registry, its wiring into
the auth cache invalidators (logout/revoke/password-change), and the
``_still_valid`` backstop that each stream polls for idle expiry.
"""
from __future__ import annotations

import asyncio

import pytest

from app import auth as auth_module
from app.auth import Actor
from app.core.ws_registry import WSRegistry, get_ws_registry
from app.db.models import AdminSession, AdminUser, ApiKey
from app.utils.time import utc_now

pytestmark = pytest.mark.anyio


class FakeWS:
    def __init__(self) -> None:
        self.closed = False
        self.code: int | None = None

    async def close(self, code: int | None = None, reason: str | None = None) -> None:
        self.closed = True
        self.code = code


# ── registry: closes only the matching streams ───────────────────


async def test_registry_close_session_is_targeted():
    reg = WSRegistry()
    a, b, c = FakeWS(), FakeWS(), FakeWS()
    reg.register(a, session_id=1, user_id=10)
    reg.register(b, session_id=2, user_id=20)
    reg.register(c, key_id=5)
    reg.close_session(1)
    await asyncio.sleep(0)  # let the scheduled close task run
    assert a.closed is True
    assert b.closed is False and c.closed is False


async def test_registry_close_user_hits_all_their_sessions():
    reg = WSRegistry()
    a, b, other = FakeWS(), FakeWS(), FakeWS()
    reg.register(a, session_id=1, user_id=10)
    reg.register(b, session_id=2, user_id=10)
    reg.register(other, session_id=3, user_id=99)
    reg.close_user(10)
    await asyncio.sleep(0)
    assert a.closed and b.closed
    assert other.closed is False


async def test_registry_close_key_and_unregister():
    reg = WSRegistry()
    k = FakeWS()
    h = reg.register(k, key_id=7)
    reg.unregister(h)
    reg.close_key(7)            # already unregistered → no-op
    await asyncio.sleep(0)
    assert k.closed is False


# ── auth invalidators drive the registry ──────────────────────────


async def test_logout_closes_that_session_stream():
    reg = get_ws_registry()
    ws = FakeWS()
    h = reg.register(ws, session_id=4242, user_id=7)
    try:
        auth_module.invalidate_session_cache(session_id=4242)
        await asyncio.sleep(0)
        assert ws.closed is True
    finally:
        reg.unregister(h)


async def test_password_change_closes_all_user_streams():
    reg = get_ws_registry()
    ws = FakeWS()
    h = reg.register(ws, session_id=5151, user_id=77)
    try:
        auth_module.invalidate_session_cache(user_id=77)  # password change path
        await asyncio.sleep(0)
        assert ws.closed is True
    finally:
        reg.unregister(h)


async def test_key_revoke_closes_key_stream():
    reg = get_ws_registry()
    ws = FakeWS()
    h = reg.register(ws, key_id=888)
    try:
        auth_module.invalidate_key_cache(888)
        await asyncio.sleep(0)
        assert ws.closed is True
    finally:
        reg.unregister(h)


# ── _still_valid backstop (idle expiry / revoke / disable) ────────


async def _mk_user_session(db_session, *, revoked=False, expired=False, active=True):
    user = AdminUser(
        username="wsuser", password_hash="x", role="admin",
        is_active=active, must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    now = utc_now()
    from datetime import timedelta
    sess = AdminSession(
        user_id=user.id, token_hash="h" * 64, csrf_token="c",
        created_at=now, last_seen_at=now,
        expires_at=now - timedelta(hours=1) if expired else now + timedelta(hours=1),
        revoked_at=now if revoked else None,
    )
    db_session.add(sess)
    await db_session.commit()
    actor = Actor(kind="user", id=user.id, name=user.username,
                  scopes=frozenset({"read"}), session_id=sess.id)
    return actor


async def test_still_valid_true_for_live_session(db_session):
    from app.api.v1.state import _still_valid
    actor = await _mk_user_session(db_session)
    assert await _still_valid(actor) is True


async def test_still_valid_false_when_revoked(db_session):
    from app.api.v1.state import _still_valid
    actor = await _mk_user_session(db_session, revoked=True)
    assert await _still_valid(actor) is False


async def test_still_valid_false_when_expired(db_session):
    from app.api.v1.state import _still_valid
    actor = await _mk_user_session(db_session, expired=True)
    assert await _still_valid(actor) is False


async def test_still_valid_false_when_user_deactivated(db_session):
    from app.api.v1.state import _still_valid
    actor = await _mk_user_session(db_session, active=False)
    assert await _still_valid(actor) is False


async def test_still_valid_key_states(db_session):
    from datetime import timedelta

    from app.api.v1.state import _still_valid
    live = ApiKey(name="k-live", key_prefix="aaaaaaaa", key_hash="x",
                  scopes=["read"], enabled=True)
    disabled = ApiKey(name="k-off", key_prefix="bbbbbbbb", key_hash="x",
                      scopes=["read"], enabled=False)
    expired = ApiKey(name="k-exp", key_prefix="cccccccc", key_hash="x",
                     scopes=["read"], enabled=True,
                     expires_at=utc_now() - timedelta(days=1))
    db_session.add_all([live, disabled, expired])
    await db_session.commit()

    def actor(k):
        return Actor(kind="api_key", id=k.id, name=k.name, scopes=frozenset(k.scopes))

    assert await _still_valid(actor(live)) is True
    assert await _still_valid(actor(disabled)) is False
    assert await _still_valid(actor(expired)) is False


async def test_still_valid_false_when_read_scope_removed(db_session):
    """F06: a key without the `read` scope must not keep a live stream — the
    revalidation enforces the current scope, not only enabled/expiry."""
    from app.api.v1.state import _still_valid
    with_read = ApiKey(name="k-rd", key_prefix="dddddddd", key_hash="x",
                       scopes=["read", "fire"], enabled=True)
    no_read = ApiKey(name="k-nord", key_prefix="eeeeeeee", key_hash="x",
                     scopes=["fire"], enabled=True)
    db_session.add_all([with_read, no_read])
    await db_session.commit()

    def actor(k):
        return Actor(kind="api_key", id=k.id, name=k.name, scopes=frozenset(k.scopes))

    assert await _still_valid(actor(with_read)) is True
    assert await _still_valid(actor(no_read)) is False


# ── F05: an in-flight verify must not re-cache a revoked key ──────

def test_cache_fill_barred_after_revocation_generation_bumps():
    """A verify captures the generation before its DB read; if a revocation
    bumps the generation while bcrypt runs, the cache fill is dropped so the
    just-revoked key is not restored for the TTL (audit F05)."""
    raw = "x" * 32
    actor = Actor(kind="api_key", id=4242, name="racer", scopes=frozenset({"read"}))
    # Clear any residue and record the generation this "verify" started with.
    auth_module.invalidate_key_cache(None)
    gen0 = auth_module._key_cache_generation()

    # Revocation commits mid-verify → generation advances.
    auth_module.invalidate_key_cache(key_id=4242)
    assert auth_module._key_cache_generation() != gen0

    # The in-flight verify now tries to fill the cache with its stale gen.
    auth_module._key_cache_set(raw, actor, None, gen=gen0)
    assert auth_module._key_cache_get(raw) is None  # fill was barred


def test_cache_fill_succeeds_with_current_generation():
    raw = "y" * 32
    actor = Actor(kind="api_key", id=99, name="ok", scopes=frozenset({"read"}))
    auth_module.invalidate_key_cache(None)
    gen = auth_module._key_cache_generation()
    auth_module._key_cache_set(raw, actor, None, gen=gen)
    cached = auth_module._key_cache_get(raw)
    assert cached is not None
    assert cached.id == 99
    auth_module.invalidate_key_cache(None)  # cleanup


# ── A-11: close the handshake/registration race ──────────────────


async def test_stream_closes_if_revoked_between_auth_and_registration(monkeypatch):
    """A revoke that commits after authentication but before the stream is
    registered finds no stream to close; the post-registration recheck must
    then close it so the race can't leave a revoked stream alive (A-11)."""
    from unittest.mock import AsyncMock

    from app import channels as _channels_pkg  # noqa: F401 - ensure pkg import
    from app.api.v1 import state

    class WS(FakeWS):
        def __init__(self) -> None:
            super().__init__()
            self.sent: list[str] = []

        async def accept(self) -> None:
            ...

        async def send_text(self, s: str) -> None:
            self.sent.append(s)

        async def receive_text(self) -> str:  # pragma: no cover - must not run
            raise AssertionError("stream must close before entering the receive loop")

    actor = Actor(kind="user", id=1, name="admin", scopes=frozenset({"admin"}), session_id=77)

    class _FakeBroadcaster:
        async def register(self, ws):
            return object()

        async def unregister(self, h):
            ...

    monkeypatch.setattr(state, "_ws_authenticate", AsyncMock(return_value=actor))
    # Simulate "revoked before registration": the DB recheck fails.
    monkeypatch.setattr(state, "_still_valid", AsyncMock(return_value=False))
    monkeypatch.setattr("app.channels.ui.get_broadcaster", lambda: _FakeBroadcaster())

    ws = WS()
    await state.stream_notifications(ws)

    assert ws.closed is True
    assert ws.code == 1008  # WS_1008_POLICY_VIOLATION
    # The stream was unregistered, so no live stream lingers for session 77.
    assert get_ws_registry().close_session(77) == 0
