"""A-11: a cold session lookup must not restore a just-revoked session.

Before the revocation generation, a lookup that started before a concurrent
logout/revoke could finish afterwards and repopulate the cache with a
valid-looking actor, keeping a revoked session alive for the cache TTL.
These tests model exactly that read / invalidate / fill ordering.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import auth
from app.auth import Actor, SessionContext, invalidate_session_cache, session_token_hash
from app.utils.time import utc_now


@pytest.fixture(autouse=True)
def _clean_session_cache():
    invalidate_session_cache()
    yield
    invalidate_session_cache()


def _session(*, session_id: int, user_id: int) -> tuple[Actor, SessionContext]:
    now = utc_now()
    actor = Actor(
        kind="user", id=user_id, name="admin",
        scopes=frozenset({"admin"}), session_id=session_id,
    )
    ctx = SessionContext(
        session_id=session_id, user_id=user_id, username="admin",
        csrf_token="tok", must_change_password=False,
        created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
    )
    return actor, ctx


def test_in_flight_fill_skipped_after_revocation():
    raw = "s" * 32
    fp = session_token_hash(raw)
    actor, ctx = _session(session_id=1, user_id=1)

    # A cold lookup captured the generation before its DB read …
    gen = auth._session_cache_generation()
    # … then a concurrent logout/revoke committed (drops cache, bumps gen) …
    invalidate_session_cache(session_id=1)
    # … and only now does the in-flight lookup try to fill the cache.
    auth._session_cache_set(fp, actor, ctx, gen)

    assert auth._session_cache_get(fp) is None, "a revoked session must not be restored"


def test_fill_succeeds_without_an_intervening_revocation():
    raw = "t" * 32
    fp = session_token_hash(raw)
    actor, ctx = _session(session_id=2, user_id=2)

    gen = auth._session_cache_generation()
    auth._session_cache_set(fp, actor, ctx, gen)

    got = auth._session_cache_get(fp)
    assert got is not None
    assert got[0].session_id == 2


def test_fill_without_generation_still_works():
    # The legacy call form (no gen) must keep caching — only an explicit stale
    # generation suppresses the fill.
    raw = "u" * 32
    fp = session_token_hash(raw)
    actor, ctx = _session(session_id=3, user_id=3)
    auth._session_cache_set(fp, actor, ctx)
    assert auth._session_cache_get(fp) is not None


def test_invalidate_bumps_the_session_generation():
    g0 = auth._session_cache_generation()
    invalidate_session_cache(session_id=123)
    assert auth._session_cache_generation() == g0 + 1
    invalidate_session_cache()  # clear-all branch bumps too
    assert auth._session_cache_generation() == g0 + 2
