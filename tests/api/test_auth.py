"""``/v1/auth`` — browser login, sessions, CSRF, lockout, password change.

SQLite-backed (``db_client``). httpx keeps the cookie jar per client, so
a logged-in client behaves like a browser tab.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app import auth as auth_module
from app.auth import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.passwords import hash_password
from app.db.models import AdminSession, AdminUser, AuditLog
from app.utils.time import utc_now

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "an-even-longer-new-password"


@pytest.fixture(autouse=True)
def _clean_session_cache():
    auth_module.invalidate_session_cache()
    yield
    auth_module.invalidate_session_cache()


@pytest.fixture
async def admin_user(db_session) -> AdminUser:
    user = AdminUser(
        id=1, username="admin", password_hash=hash_password(PASSWORD),
        role="admin", is_active=True, must_change_password=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, username="admin", password=PASSWORD):
    return await client.post("/v1/auth/login", json={"username": username, "password": password})


@pytest.fixture
async def logged_in(db_client, admin_user):
    """Client with a live session; returns (client, csrf_headers)."""
    r = await _login(db_client)
    assert r.status_code == 200, r.text
    csrf = r.json()["csrf_token"]
    return db_client, {CSRF_HEADER: csrf}


# ── Login ─────────────────────────────────────────────────────────


async def test_login_sets_cookies_and_returns_user(db_client, admin_user):
    r = await _login(db_client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == "admin"
    assert body["user"]["must_change_password"] is False
    assert body["csrf_token"]
    assert db_client.cookies.get(SESSION_COOKIE)
    assert db_client.cookies.get(CSRF_COOKIE) == body["csrf_token"]

    set_cookie = "; ".join(r.headers.get_list("set-cookie"))
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie.lower().replace("samesite=strict", "SameSite=strict")
    assert "Path=/" in set_cookie


async def test_login_wrong_password_and_unknown_user_look_identical(db_client, admin_user):
    r1 = await _login(db_client, password="wrong-password-here")
    r2 = await _login(db_client, username="nobody", password="wrong-password-here")
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"]["code"] == r2.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert r1.json()["detail"]["message"] == r2.json()["detail"]["message"]
    assert not db_client.cookies.get(SESSION_COOKIE)


async def test_login_disabled_account_rejected(db_client, db_session, admin_user):
    admin_user.is_active = False
    await db_session.commit()
    assert (await _login(db_client)).status_code == 401


async def test_login_failures_are_audited_without_password(db_client, db_session, admin_user):
    await _login(db_client, password="wrong-password-here")
    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert [r.action for r in rows] == ["auth.login_failed"]
    assert rows[0].actor_kind.value == "system"
    assert "wrong-password-here" not in str(rows[0].after)


async def test_lockout_after_max_failures(db_client, admin_user):
    for _ in range(5):
        assert (await _login(db_client, password="wrong-password-here")).status_code == 401
    r = await _login(db_client)  # correct password, but locked
    assert r.status_code == 423
    assert r.json()["detail"]["code"] == "LOCKED_OUT"
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["detail"]["retry_after_sec"] >= 1


async def test_a_remote_guesser_does_not_lock_the_admin_out_of_the_lan(db_client, db_session, admin_user, monkeypatch):
    """Review F8: five tries from anywhere locked the username everywhere.
    Now they lock it where they came from; a lock is audited once, not once
    per refused attempt (review F5)."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_cidrs", "127.0.0.0/8")

    async def login(ip: str, password: str):
        return await db_client.post("/v1/auth/login", json={"username": "admin", "password": password},
                                    headers={"X-Forwarded-For": ip})

    for _ in range(5):
        assert (await login("198.51.100.7", "wrong-password-here")).status_code == 401
    assert [(await login("198.51.100.7", "wrong-password-here")).status_code for _ in range(3)] == [423] * 3
    assert (await login("192.168.1.20", PASSWORD)).status_code == 200
    blocked = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "auth.login_blocked"))).scalars().all()
    assert len(blocked) == 1


# ── Session use: scope, CSRF, must-change ─────────────────────────


async def test_session_cookie_grants_admin_scope(logged_in):
    client, csrf = logged_in
    assert (await client.get("/v1/templates")).status_code == 200
    assert (await client.get("/v1/api_keys")).status_code == 200  # admin-only


async def test_write_without_csrf_header_is_403(logged_in):
    client, _ = logged_in
    r = await client.post("/v1/channels", json={"name": "c1", "kind": "ui"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "CSRF_FAILED"


async def test_write_with_wrong_csrf_is_403(logged_in):
    client, _ = logged_in
    r = await client.post("/v1/channels", json={"name": "c1", "kind": "ui"},
                          headers={CSRF_HEADER: "nope"})
    assert r.status_code == 403


async def test_write_with_csrf_header_succeeds_and_audits_user(logged_in, db_session):
    client, csrf = logged_in
    r = await client.post("/v1/channels", json={"name": "c1", "kind": "ui"}, headers=csrf)
    assert r.status_code == 201, r.text
    row = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "channel.create"))
    ).scalar_one()
    assert row.actor_kind.value == "user"
    assert row.actor_name == "admin"


async def test_cross_site_fetch_metadata_is_403(logged_in):
    client, csrf = logged_in
    r = await client.post("/v1/channels", json={"name": "c1", "kind": "ui"},
                          headers={**csrf, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = await client.post("/v1/channels", json={"name": "c1", "kind": "ui"},
                          headers={**csrf, "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = await client.post("/v1/channels", json={"name": "c1", "kind": "ui"},
                          headers={**csrf, "Origin": "http://testserver",
                                   "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 201


async def test_api_key_path_is_unaffected_by_csrf(db_client, admin_key, admin_user):
    r = await db_client.post("/v1/channels", json={"name": "c2", "kind": "ui"},
                             headers={"X-API-Key": admin_key})
    assert r.status_code == 201


async def test_api_key_cannot_use_session_endpoints(db_client, admin_key, admin_user):
    h = {"X-API-Key": admin_key}
    assert (await db_client.get("/v1/auth/me", headers=h)).status_code == 403
    r = await db_client.post("/v1/auth/password", headers=h,
                             json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SESSION_REQUIRED"


async def test_must_change_password_blocks_writes_but_not_reads(db_client, db_session, admin_user):
    admin_user.must_change_password = True
    await db_session.commit()
    r = await _login(db_client)
    assert r.json()["user"]["must_change_password"] is True
    csrf = {CSRF_HEADER: r.json()["csrf_token"]}

    assert (await db_client.get("/v1/templates")).status_code == 200
    assert (await db_client.get("/v1/auth/me")).status_code == 200
    r = await db_client.post("/v1/channels", json={"name": "c1", "kind": "ui"}, headers=csrf)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    r = await db_client.post("/v1/auth/password", headers=csrf,
                             json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 204, r.text
    r = await db_client.post("/v1/channels", json={"name": "c1", "kind": "ui"}, headers=csrf)
    assert r.status_code == 201


# ── /me, password, sessions, logout ───────────────────────────────


async def test_me_reports_user_and_current_session(logged_in):
    client, _ = logged_in
    r = await client.get("/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["username"] == "admin"
    assert body["scopes"] == ["admin"]
    assert body["session"]["current"] is True
    assert body["session"]["expires_at"].endswith("Z")


async def test_password_change_requires_current_and_policy(logged_in):
    client, csrf = logged_in
    r = await client.post("/v1/auth/password", headers=csrf,
                          json={"current_password": "wrong-current-pw", "new_password": NEW_PASSWORD})
    assert r.status_code == 401
    r = await client.post("/v1/auth/password", headers=csrf,
                          json={"current_password": PASSWORD, "new_password": "short"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "PASSWORD_POLICY"
    r = await client.post("/v1/auth/password", headers=csrf,
                          json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert r.status_code == 400


async def test_password_change_revokes_other_sessions(db_client, admin_user, db_engine):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    r = await _login(db_client)
    csrf = {CSRF_HEADER: r.json()["csrf_token"]}
    # Second "browser"
    other = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://testserver")
    assert (await _login(other)).status_code == 200
    assert (await other.get("/v1/auth/me")).status_code == 200

    r = await db_client.post("/v1/auth/password", headers=csrf,
                             json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 204
    assert (await db_client.get("/v1/auth/me")).status_code == 200  # current survives
    assert (await other.get("/v1/auth/me")).status_code == 401  # other is dead
    # New password works, old does not
    await other.aclose()
    assert (await _login(db_client, password=PASSWORD)).status_code == 401
    assert (await _login(db_client, password=NEW_PASSWORD)).status_code == 200


async def test_sessions_list_and_revoke(db_client, admin_user, db_engine):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    r = await _login(db_client)
    csrf = {CSRF_HEADER: r.json()["csrf_token"]}
    other = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://testserver")
    await _login(other)

    r = await db_client.get("/v1/auth/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 2
    assert sum(s["current"] for s in sessions) == 1
    other_id = next(s["id"] for s in sessions if not s["current"])

    assert (await db_client.delete(f"/v1/auth/sessions/{other_id}", headers=csrf)).status_code == 204
    assert (await other.get("/v1/auth/me")).status_code == 401
    assert (await db_client.delete("/v1/auth/sessions/999", headers=csrf)).status_code == 404

    await _login(other)
    r = await db_client.delete("/v1/auth/sessions", headers=csrf)
    assert r.status_code == 200
    assert r.json()["revoked"] == 1
    assert (await other.get("/v1/auth/me")).status_code == 401
    await other.aclose()


async def test_logout_revokes_and_clears_cookies(logged_in, db_session):
    client, csrf = logged_in
    r = await client.post("/v1/auth/logout", headers=csrf)
    assert r.status_code == 204
    assert not client.cookies.get(SESSION_COOKIE)
    assert (await client.get("/v1/auth/me")).status_code == 401
    row = (await db_session.execute(select(AdminSession))).scalar_one()
    await db_session.refresh(row)
    assert row.revoked_at is not None


async def test_expired_session_is_rejected(logged_in, db_session):
    client, _ = logged_in
    auth_module.invalidate_session_cache()
    row = (await db_session.execute(select(AdminSession))).scalar_one()
    row.expires_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    r = await client.get("/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "SESSION_INVALID"


async def test_garbage_cookie_is_401(db_client, admin_user):
    db_client.cookies.set(SESSION_COOKIE, "x" * 40)
    assert (await db_client.get("/v1/templates")).status_code == 401
    db_client.cookies.set(SESSION_COOKIE, "short")
    assert (await db_client.get("/v1/templates")).status_code == 401


async def test_no_credentials_still_401(db_client, admin_user):
    assert (await db_client.get("/v1/templates")).status_code == 401


async def test_me_says_which_address_klopot_sees(db_client, admin_user, monkeypatch):
    """The admin UI's "Add my address" (API key allowlist) needs the address
    as Klopot sees it — behind a trusted proxy, the client's, not the proxy's."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_cidrs", "127.0.0.0/8")
    assert (await _login(db_client)).status_code == 200
    me = (await db_client.get("/v1/auth/me", headers={"X-Forwarded-For": "203.0.113.7"})).json()
    assert me["client_ip"] == "203.0.113.7"
