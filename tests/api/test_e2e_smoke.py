"""End-to-end smoke (F10): the full admin flow over a real browser
session — login → create channel → template → route → rule → fire test →
log → ack → API key create/rotate/revoke → logout → 401.

In-process httpx (``db_client``, SQLite) with the session cookie jar, so
the client behaves like a browser tab (cookies + CSRF double-submit).
Complements the MySQL curl smoke in CI (which exercises the X-API-Key
path). One test, asserted step by step, so a break names the stage.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app import auth as auth_module
from app.auth import CSRF_HEADER, SESSION_COOKIE
from app.core.passwords import hash_password
from app.db.models import AdminUser

PASSWORD = "e2e-correct-horse-battery"


@pytest.fixture(autouse=True)
def _clean_session_cache():
    auth_module.invalidate_session_cache()
    yield
    auth_module.invalidate_session_cache()


@pytest.fixture
async def seeded_admin(db_session) -> AdminUser:
    user = AdminUser(
        id=1, username="admin", password_hash=hash_password(PASSWORD),
        role="admin", is_active=True, must_change_password=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
def no_engine_reload():
    """Rule create/delete hot-reloads the engine; stub it (no lifespan in tests)."""
    with patch("app.api.v1.rules.get_engine") as ge:
        ge.return_value.reload_rules = AsyncMock()
        yield ge


async def test_full_admin_flow(db_client, seeded_admin, no_engine_reload):
    c = db_client

    # 1. login → session cookie + csrf token
    r = await c.post("/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200, r.text
    h = {CSRF_HEADER: r.json()["csrf_token"]}
    assert c.cookies.get(SESSION_COOKIE)

    # 2. create a ui channel
    r = await c.post("/v1/channels", json={"name": "e2e_ui", "kind": "ui"}, headers=h)
    assert r.status_code == 201, r.text

    # 3. create a template
    r = await c.post("/v1/templates", json={
        "type": "e2e_alert", "severity": "warning",
        "title_template": "E2E {name}", "message_template": "value={value}",
        "min_repeat_min": 0,
    }, headers=h)
    assert r.status_code == 201, r.text

    # 4. route the template → channel (atomic PUT replace)
    r = await c.put("/v1/templates/e2e_alert/channels",
                    json=[{"channel_name": "e2e_ui", "severity_min": "info"}], headers=h)
    assert r.status_code == 200, r.text
    assert [x["channel_name"] for x in r.json()] == ["e2e_ui"]

    # 5. create a rule for the template
    r = await c.post("/v1/rules", json={
        "name": "e2e_rule", "template_type": "e2e_alert",
        "condition_expr": "True", "persist_n": 1, "eval_interval_sec": 10,
    }, headers=h)
    assert r.status_code == 201, r.text

    # 6. fire it (test) → a log row is written
    r = await c.post("/v1/fire", json={
        "type": "e2e_alert", "context": {"name": "pack1", "value": 42}, "test": True,
    }, headers=h)
    assert r.status_code == 202, r.text
    fire_id = r.json()["id"]

    # 7. the log row exists and rendered the context
    r = await c.get(f"/v1/log/{fire_id}")
    assert r.status_code == 200, r.text
    entry = r.json()
    assert entry["type"] == "e2e_alert"
    assert "pack1" in entry["title"]

    # 8. acknowledge it
    r = await c.post(f"/v1/log/{fire_id}/ack", headers=h)
    assert r.status_code == 200, r.text

    # 9. API key lifecycle: create (plaintext once) → rotate → revoke
    r = await c.post("/v1/api_keys", json={"name": "e2e_key", "scopes": ["fire"]}, headers=h)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["key"], "plaintext returned once on create"
    kid = created["id"]

    r = await c.post(f"/v1/api_keys/{kid}/rotate", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["key"], "new plaintext on rotate"
    new_kid = r.json()["id"]

    r = await c.patch(f"/v1/api_keys/{new_kid}", json={"enabled": False}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False

    # 10. still authenticated, then logout → subsequent call is 401
    assert (await c.get("/v1/auth/me")).status_code == 200
    r = await c.post("/v1/auth/logout", headers=h)
    assert r.status_code in (200, 204), r.text
    assert (await c.get("/v1/auth/me")).status_code == 401


async def test_csrf_required_on_cookie_write(db_client, seeded_admin):
    """A cookie-authenticated write without the CSRF header is rejected —
    the property the whole session model leans on."""
    c = db_client
    r = await c.post("/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200
    # No X-CSRF-Token header → 403
    r = await c.post("/v1/channels", json={"name": "nope", "kind": "ui"})
    assert r.status_code == 403, r.text
