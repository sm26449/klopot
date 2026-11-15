"""API reference: /openapi.json, /docs, /redoc (app.api.docs).

Public when docs are enabled (dev); otherwise only for an authenticated
caller — admin-UI session or X-API-Key (S-12 keeps anonymous access closed).
The schema carries ``x-required-scope`` per operation.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app import auth as auth_module
from app.config import get_settings
from app.core.passwords import hash_password
from app.db.models import AdminUser
from app.main import create_app

PASSWORD = "correct-horse-battery-staple"
REFERENCE_PATHS = ("/openapi.json", "/docs", "/redoc")


@pytest.fixture(autouse=True)
def _clean_session_cache():
    auth_module.invalidate_session_cache()
    yield
    auth_module.invalidate_session_cache()


@pytest.fixture
async def closed_client(db_engine, monkeypatch) -> AsyncIterator[AsyncClient]:
    """Client for an app built with the public docs OFF (a prod deploy)."""
    monkeypatch.setenv("ALERTD_DOCS_ENABLED", "false")
    get_settings.cache_clear()
    try:
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            yield c
    finally:
        monkeypatch.delenv("ALERTD_DOCS_ENABLED")
        get_settings.cache_clear()


@pytest.fixture
async def admin_user(db_session) -> AdminUser:
    user = AdminUser(
        id=1, username="admin", password_hash=hash_password(PASSWORD),
        role="admin", is_active=True, must_change_password=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.parametrize("path", ["/openapi.json"])
async def test_anonymous_gets_401_on_schema_when_closed(closed_client, path):
    r = await closed_client.get(path)
    assert r.status_code == 401
    assert "paths" not in r.text


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
async def test_anonymous_html_redirects_to_login_when_closed(closed_client, path):
    r = await closed_client.get(path)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/"


@pytest.mark.parametrize("path", REFERENCE_PATHS)
async def test_session_user_gets_reference_when_closed(closed_client, admin_user, path):
    login = await closed_client.post("/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert login.status_code == 200, login.text
    r = await closed_client.get(path)
    assert r.status_code == 200


@pytest.mark.parametrize("path", REFERENCE_PATHS)
async def test_api_key_gets_reference_when_closed(closed_client, admin_key, path):
    r = await closed_client.get(path, headers={"X-API-Key": admin_key})
    assert r.status_code == 200


async def test_invalid_api_key_is_refused_when_closed(closed_client, admin_key):
    r = await closed_client.get("/openapi.json", headers={"X-API-Key": "alertd_not_a_real_key_000000"})
    assert r.status_code == 401


@pytest.mark.parametrize("path", REFERENCE_PATHS)
async def test_public_when_docs_enabled(db_client, path):
    # The test env runs with ALERTD_COOKIE_SECURE=false → docs auto-public.
    assert get_settings().docs_enabled_effective
    r = await db_client.get(path)
    assert r.status_code == 200


async def test_schema_carries_required_scopes(db_client):
    spec = (await db_client.get("/openapi.json")).json()
    ops = spec["paths"]
    assert ops["/v1/fire"]["post"]["x-required-scope"] == "fire"
    assert ops["/v1/rules"]["get"]["x-required-scope"] == "read"
    assert ops["/v1/rules"]["post"]["x-required-scope"] == "admin"
    assert ops["/v1/auth/password"]["post"]["x-required-scope"] == "session"
    assert "x-required-scope" not in ops["/v1/health"]["get"]
    # The reference routes themselves are not part of the documented surface.
    assert not {"/openapi.json", "/docs", "/redoc"} & set(ops)


async def test_swagger_shows_scope_extension(db_client):
    html = (await db_client.get("/docs")).text
    assert '"showExtensions": true' in html
    assert "/openapi.json" in html
