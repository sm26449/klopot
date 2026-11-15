"""A-13: WebSocket revalidation must honor the scope hierarchy.

Both live streams poll ``_still_valid`` to drop a connection whose key lost
access. It checked literal ``read`` membership, so an admin-only key — which
passes the initial ``read``-scoped handshake because ``admin`` implies ``read``
— was closed on the first revalidation and reconnected into the same drop every
cycle. The fix reuses the central ``scope_grants`` hierarchy, so an admin-only
key keeps its stream while a key with neither ``read`` nor ``admin`` is still
dropped (the F06 guard).
"""
from __future__ import annotations

import pytest

from app.api.v1.state import _still_valid
from app.auth import Actor
from app.db.models import ApiKey

pytestmark = pytest.mark.anyio


def _actor(k: ApiKey) -> Actor:
    return Actor(kind="api_key", id=k.id, name=k.name, scopes=frozenset(k.scopes))


async def test_admin_only_key_keeps_its_stream(db_session):
    """The fix: admin implies read, so an admin-only key is not dropped on
    revalidation (negative control: the old literal check returned False here)."""
    k = ApiKey(name="k-admin", key_prefix="ffffffff", key_hash="x",
               scopes=["admin"], enabled=True)
    db_session.add(k)
    await db_session.commit()
    assert await _still_valid(_actor(k)) is True


async def test_read_key_keeps_its_stream(db_session):
    k = ApiKey(name="k-read", key_prefix="aaaaaaaa", key_hash="x",
               scopes=["read"], enabled=True)
    db_session.add(k)
    await db_session.commit()
    assert await _still_valid(_actor(k)) is True


async def test_key_without_read_or_admin_is_still_dropped(db_session):
    """Regression guard for F06: the hierarchy fix must NOT re-admit a key that
    has neither read nor admin."""
    k = ApiKey(name="k-fire", key_prefix="eeeeeeee", key_hash="x",
               scopes=["fire"], enabled=True)
    db_session.add(k)
    await db_session.commit()
    assert await _still_valid(_actor(k)) is False
