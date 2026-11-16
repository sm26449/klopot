"""Admin UI shell (phase F2): static mount, headers, feature flag, WS cookie auth."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin_ui import SECURITY_HEADERS, STATIC_DIR
from app.config import get_settings
from tests._ws import WsClosed, ws_connect


async def test_index_served_with_security_headers(client):
    r = await client.get("/admin/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Klopot admin" in r.text
    for k, v in SECURITY_HEADERS.items():
        assert r.headers.get(k) == v, k
    csp = r.headers["content-security-policy"]
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "script-src 'self'" in csp


async def test_admin_without_slash_redirects(client):
    r = await client.get("/admin", follow_redirects=False)
    assert r.status_code in (301, 307, 308)
    assert r.headers["location"].endswith("/admin/")


async def test_assets_served_and_unknown_404(client):
    for path in ("/admin/app.js", "/admin/styles.css", "/admin/vendor/preact.module.js",
                 "/admin/lib/api.js", "/admin/views/login.js"):
        r = await client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "no-cache"
    assert (await client.get("/admin/nope.js")).status_code == 404


async def test_installable_app_files_are_served(client):
    """docs/WEB_PUSH.md: manifest + service worker + icons, allowed by the CSP."""
    import json

    m = await client.get("/admin/manifest.webmanifest")
    assert m.status_code == 200 and m.headers["content-type"].startswith("application/manifest+json")
    manifest = json.loads(m.text)
    assert manifest["scope"] == "/admin/" and manifest["display"] == "standalone"
    for icon in manifest["icons"]:
        assert (await client.get(f"/admin/{icon['src']}")).status_code == 200
    assert any(i["purpose"] == "maskable" for i in manifest["icons"])
    sw = await client.get("/admin/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert sw.headers["cache-control"] == "no-cache"
    # No offline cache: the worker never intercepts requests.
    assert '"fetch"' not in sw.text and "caches." not in sw.text
    csp = SECURITY_HEADERS["Content-Security-Policy"]
    assert "manifest-src 'self'" in csp and "worker-src 'self'" in csp
    html = (STATIC_DIR / "index.html").read_text()
    assert 'rel="manifest"' in html and 'rel="apple-touch-icon"' in html
    assert (await client.get("/admin/icons/apple-touch-icon.png")).status_code == 200


def test_index_has_no_inline_script_or_style():
    """The CSP forbids inline code; the HTML must not rely on any."""
    html = (STATIC_DIR / "index.html").read_text()
    assert "<script>" not in html
    assert "javascript:" not in html
    assert " style=" not in html
    assert "onclick" not in html.lower()


def test_static_js_has_no_remote_imports():
    """No CDN at runtime: every import is relative."""
    import re

    for path in STATIC_DIR.rglob("*.js"):
        if "vendor" in path.parts:
            continue
        for m in re.finditer(r"""from\s+["']([^"']+)["']""", path.read_text()):
            assert m.group(1).startswith("./") or m.group(1).startswith("../"), (path, m.group(1))


async def test_api_responses_get_baseline_headers(client):
    r = await client.get("/v1/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert "content-security-policy" not in r.headers  # Swagger needs none


async def test_flag_off_unmounts_ui(monkeypatch):
    monkeypatch.setenv("ALERTD_ADMIN_UI_ENABLED", "false")
    get_settings.cache_clear()
    try:
        from app.main import create_app

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            assert (await c.get("/admin/")).status_code == 404
            assert (await c.get("/v1/health")).status_code == 200
    finally:
        monkeypatch.delenv("ALERTD_ADMIN_UI_ENABLED", raising=False)
        get_settings.cache_clear()


# ── WebSocket auth: cookie or api_key ─────────────────────────────


@pytest.fixture
async def ws_app(db_engine):
    from app.main import create_app

    return create_app()


async def _login_cookie(app) -> str:
    """Create an admin user + session through the API; return the cookie."""
    from app.auth import SESSION_COOKIE
    from app.core.passwords import hash_password
    from app.db import session as session_module
    from app.db.models import AdminUser

    async with session_module._session_factory() as s:
        s.add(AdminUser(id=1, username="admin", password_hash=hash_password("correct-horse-battery"),
                        must_change_password=False))
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.post("/v1/auth/login", json={"username": "admin", "password": "correct-horse-battery"})
        assert r.status_code == 200
        return c.cookies.get(SESSION_COOKIE)


async def test_ws_rejects_without_credentials(ws_app):
    with pytest.raises(WsClosed) as ei:
        async with ws_connect(ws_app, "/v1/stream/state"):
            pass
    assert ei.value.code == 1008


async def test_ws_accepts_session_cookie_and_checks_origin(ws_app):
    import json

    from app import auth as auth_module
    from app.auth import SESSION_COOKIE

    auth_module.invalidate_session_cache()
    cookie = await _login_cookie(ws_app)
    hdr = {"cookie": f"{SESSION_COOKIE}={cookie}"}

    async with ws_connect(ws_app, "/v1/stream/state", headers=hdr) as ws:
        assert json.loads(await ws.receive_text())["type"] == "hello"

    # Cross-origin handshake with a valid cookie is refused (WS ignores SameSite)
    with pytest.raises(WsClosed) as ei:
        async with ws_connect(ws_app, "/v1/stream/state", headers={**hdr, "origin": "https://evil.example"}):
            pass
    assert ei.value.code == 1008

    # Same-origin Origin header passes
    async with ws_connect(ws_app, "/v1/stream/notifications", headers={**hdr, "origin": "http://testserver"}) as ws:
        assert json.loads(await ws.receive_text())["type"] == "hello"


def test_ui_meta_kinds_fixture_matches_the_server() -> None:
    """tests/js/support/meta_kinds.fixture.json is what the admin-UI tests
    render forms from; it must be GET /v1/meta/kinds exactly. Regenerate:
    .venv/bin/python -c "import json; from app.meta_kinds import describe_kinds;
    open('tests/js/support/meta_kinds.fixture.json','w').write(json.dumps(describe_kinds(), indent=2, ensure_ascii=False)+'\\n')"
    """
    import json
    from pathlib import Path

    from app.meta_kinds import describe_kinds

    fixture = Path(__file__).parent / "js" / "support" / "meta_kinds.fixture.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == describe_kinds()
