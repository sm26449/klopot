"""Admin-plane allowlist (`ALERTD_ADMIN_ALLOW_CIDRS`, app/admin_allow.py).

Default deny: only `POST /v1/fire` and `POST /v1/inputs/{id}/webhook` are
open to everyone; the rest — admin UI, sign-in, health, metrics, streams,
paths that do not exist — needs a client inside the networks, judged by the
real client address (behind a trusted proxy, the one it forwarded).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin_allow import AdminAllowMiddleware, is_public
from app.config import get_settings
from app.utils.client_ip import parse_networks

LAN = parse_networks(("192.168.1.0/24",), label="t", catch_all="t")


async def _echo(scope, receive, send):
    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _client(peer: str) -> AsyncClient:
    transport = ASGITransport(app=AdminAllowMiddleware(_echo, LAN), client=(peer, 1234))
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.parametrize(("method", "path", "public"), [
    ("POST", "/v1/fire", True),
    ("POST", "/v1/inputs/12/webhook", True),
    ("GET", "/v1/fire", False),
    ("POST", "/v1/fire/", False),
    ("POST", "/V1/fire", False),
    ("POST", "/v1//fire", False),
    ("POST", "/v1/inputs/12/webhook/x", False),
    ("POST", "/v1/inputs/abc/webhook", False),
    ("POST", "/v1/auth/login", False),
    ("GET", "/v1/health", False),
    ("GET", "/admin/", False),
    ("GET", "/no/such/path", False),
])
def test_only_the_two_doors_are_public(method, path, public):
    assert is_public(method, path) is public


async def test_outside_the_networks_only_the_doors_answer():
    async with _client("203.0.113.9") as c:
        assert (await c.post("/v1/fire", json={})).status_code == 200
        assert (await c.post("/v1/inputs/3/webhook", json={})).status_code == 200
        for method, path in [("GET", "/v1/health"), ("POST", "/v1/auth/login"), ("GET", "/admin/"),
                             ("GET", "/v1/fire"), ("GET", "/nothing")]:
            r = await c.request(method, path)
            assert r.status_code == 403, (method, path)
            assert r.json()["error"]["code"] == "ADDRESS_NOT_ALLOWED"


async def test_inside_the_networks_everything_answers():
    async with _client("192.168.1.20") as c:
        assert (await c.get("/admin/")).status_code == 200
        assert (await c.post("/v1/auth/login")).status_code == 200


async def test_the_forwarded_client_is_judged_behind_a_trusted_proxy(monkeypatch):
    monkeypatch.setattr(get_settings(), "trusted_proxy_cidrs", "172.20.0.0/16")
    async with _client("172.20.0.5") as c:                     # traefik
        assert (await c.get("/admin/", headers={"X-Forwarded-For": "192.168.1.20"})).status_code == 200
        assert (await c.get("/admin/", headers={"X-Forwarded-For": "203.0.113.9"})).status_code == 403
        # A forged entry to the left changes nothing: the proxy appended the real one.
        forged = await c.get("/admin/", headers={"X-Forwarded-For": "192.168.1.20, 203.0.113.9"})
        assert forged.status_code == 403


async def test_a_websocket_from_outside_is_closed_before_it_is_accepted():
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "websocket.connect"}

    scope = {"type": "websocket", "path": "/v1/stream/notifications", "client": ("203.0.113.9", 1),
             "headers": []}
    await AdminAllowMiddleware(_echo, LAN)(scope, receive, send)
    assert sent == [{"type": "websocket.close", "code": 1008, "reason": "Not allowed from this address"}]


async def test_empty_is_off():
    transport = ASGITransport(app=AdminAllowMiddleware(_echo, ()), client=("203.0.113.9", 1))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        assert (await c.get("/admin/")).status_code == 200


def test_an_invalid_or_catch_all_list_stops_startup():
    from app.config import Settings

    for bad, message in [("10.0.0.0/8,nope", "not an IP address or CIDR"), ("0.0.0.0/0", "allows every address")]:
        with pytest.raises(ValueError, match=message):
            Settings(admin_allow_cidrs=bad)


async def test_wired_into_the_app_under_the_header_middleware(monkeypatch):
    """In the real stack the refusal still gets the security headers."""
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "admin_allow_cidrs", "192.168.1.0/24")
    app = create_app()
    transport = ASGITransport(app=app, client=("203.0.113.9", 1))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/v1/version")
        assert r.status_code == 403
        assert r.headers["x-content-type-options"] == "nosniff"      # outer middleware still runs
