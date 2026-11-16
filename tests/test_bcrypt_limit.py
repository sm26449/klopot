"""bcrypt reads at most 72 bytes of a secret (bcrypt 5 refuses more).

Older bcrypt releases cut a longer secret off silently, so a key that only
shared its first 72 bytes with a stored one passed. With bcrypt 5 hashing or
checking more raises ``ValueError``. A presented key longer than that can
match no stored hash: it is refused as a wrong key without being hashed, and
a bootstrap key that long is not seeded (it could not be hashed).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import auth
from app.config import get_settings
from app.db.models import ApiKey
from scripts.seed import seed_bootstrap_admin_key

pytestmark = pytest.mark.anyio


async def test_a_key_longer_than_bcrypt_reads_is_wrong_and_not_hashed(db_session, admin_key, monkeypatch):
    hashed: list[bytes] = []

    async def record(raw: bytes, _hashed: bytes) -> bool:
        hashed.append(raw)
        return False

    monkeypatch.setattr(auth, "_checkpw_async", record)
    too_long = admin_key + "x" * (auth.BCRYPT_MAX_BYTES - len(admin_key) + 1)   # same prefix, 73 bytes
    with pytest.raises(HTTPException) as e:
        await auth._resolve_key(too_long, db_session, "203.0.113.60")
    assert e.value.status_code == 401
    assert hashed == []
    assert auth._KEY_BUDGET.spent("203.0.113.60") is False      # counted once, like any wrong key


async def test_the_right_key_still_resolves(db_session, admin_key):
    actor = await auth._resolve_key(admin_key, db_session, "203.0.113.61")
    assert actor.kind == "api_key"


async def _seed(db_session, monkeypatch, value: str) -> ApiKey | None:
    monkeypatch.setenv("ALERTD_BOOTSTRAP_ADMIN_KEY", value)
    get_settings.cache_clear()
    try:
        await seed_bootstrap_admin_key(db_session)
        await db_session.commit()
    finally:
        get_settings.cache_clear()
    return (await db_session.execute(select(ApiKey))).scalar_one_or_none()


async def test_a_bootstrap_key_bcrypt_cannot_hash_is_not_seeded(db_session, monkeypatch):
    assert await _seed(db_session, monkeypatch, "alertd_" + "my-own-admin-key-" * 4) is None   # 75 bytes


async def test_a_bootstrap_key_of_exactly_72_bytes_is_seeded(db_session, monkeypatch):
    key = "alertd_" + "k" * (auth.BCRYPT_MAX_BYTES - len("alertd_"))
    row = await _seed(db_session, monkeypatch, key)
    assert row is not None and row.key_digest is None
