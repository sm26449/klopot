"""Bootstrap seed for the admin-UI account (decision D9)."""
from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.core.passwords import verify_password
from app.db.models import AdminUser
from scripts.seed import seed_admin_user


async def _with_bootstrap(monkeypatch, value: str):
    monkeypatch.setenv("ALERTD_ADMIN_BOOTSTRAP_PASSWORD", value)
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("ALERTD_ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    get_settings.cache_clear()


async def test_seed_creates_admin_with_forced_change(db_session, monkeypatch):
    gen = _with_bootstrap(monkeypatch, "bootstrap-password-123")
    await anext(gen)
    try:
        assert await seed_admin_user(db_session) == 1
        await db_session.commit()
        user = (await db_session.execute(select(AdminUser))).scalar_one()
        assert user.username == "admin"
        assert user.must_change_password is True
        assert verify_password(user.password_hash, "bootstrap-password-123")
        # idempotent: second run is a no-op even with the var still set
        assert await seed_admin_user(db_session) == 0
    finally:
        try:
            await anext(gen)
        except StopAsyncIteration:
            pass


async def test_seed_noop_without_var_or_with_short_password(db_session, monkeypatch):
    monkeypatch.delenv("ALERTD_ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    get_settings.cache_clear()
    assert await seed_admin_user(db_session) == 0

    gen = _with_bootstrap(monkeypatch, "short")
    await anext(gen)
    try:
        assert await seed_admin_user(db_session) == 0
        assert (await db_session.execute(select(AdminUser))).first() is None
    finally:
        try:
            await anext(gen)
        except StopAsyncIteration:
            pass
