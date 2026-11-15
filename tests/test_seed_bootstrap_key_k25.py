"""A bootstrap key in the generated shape must be as strong as a generated one (review K25).

A key shaped like a generated one (``alertd_`` + 43 URL-safe characters) is
found by its SHA-256 — fast, fine for 256 random bits, cheap to reverse for a
weak one from a leaked table. The documented way to make the bootstrap key
(``secrets.token_urlsafe(32)``) gives that shape and strength; a hand-made
key in that shape, like ``alertd_aaaa…``, got the fast hash too. The seed now
refuses one that is visibly not random; a key of any other shape stays on
bcrypt only, as before.
"""
from __future__ import annotations

import secrets

import pytest
from sqlalchemy import select

from app.auth import key_digest
from app.config import get_settings
from app.db.models import ApiKey
from scripts.seed import seed_bootstrap_admin_key

pytestmark = pytest.mark.anyio


async def _seed(db_session, monkeypatch, value: str) -> ApiKey | None:
    monkeypatch.setenv("ALERTD_BOOTSTRAP_ADMIN_KEY", value)
    get_settings.cache_clear()
    try:
        await seed_bootstrap_admin_key(db_session)
        await db_session.commit()
    finally:
        get_settings.cache_clear()
    return (await db_session.execute(select(ApiKey))).scalar_one_or_none()


async def test_a_weak_key_in_the_generated_shape_is_refused(db_session, monkeypatch):
    weak = "alertd_" + "ab" * 21 + "c"
    assert key_digest(weak) is not None           # it has the generated shape
    assert await _seed(db_session, monkeypatch, weak) is None


async def test_a_generated_key_is_seeded_with_its_digest(db_session, monkeypatch):
    strong = "alertd_" + secrets.token_urlsafe(32)
    row = await _seed(db_session, monkeypatch, strong)
    assert row is not None
    assert row.key_digest == key_digest(strong)


async def test_a_key_of_another_shape_is_bcrypt_only(db_session, monkeypatch):
    row = await _seed(db_session, monkeypatch, "alertd_my_own_admin_key_2026")
    assert row is not None
    assert row.key_digest is None
