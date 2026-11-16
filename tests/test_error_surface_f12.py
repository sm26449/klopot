"""What an error tells the caller (review F12).

The 500 handler runs outside every middleware: it echoed any X-Trace-Id
unvalidated, minted an id the request's log lines did not carry, and its
response had none of the security headers. A 409 quoted the driver
(`Duplicate entry 'x' for key 'uq_…'`).
"""
from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.logging_setup import SECURITY_HEADERS
from app.main import create_app


@pytest.fixture
async def crashing() -> AsyncClient:
    app = create_app()

    @app.get("/v1/_boom")
    async def _boom():
        raise RuntimeError("secret detail")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def test_a_500_carries_the_request_trace_and_the_security_headers(crashing, caplog):
    caplog.set_level(logging.ERROR)
    r = await crashing.get("/v1/_boom", headers={"X-Trace-Id": "abc-123"})
    assert r.status_code == 500
    assert r.json()["error"]["trace_id"] == "abc-123" == r.headers["x-trace-id"]
    assert "secret detail" not in r.text
    for name, value in SECURITY_HEADERS.items():
        assert r.headers[name] == value, name
    assert "abc-123" in caplog.text


async def test_a_500_never_echoes_an_invalid_trace_header(crashing):
    r = await crashing.get("/v1/_boom", headers={"X-Trace-Id": "<script>alert(1)</script>"})
    trace = r.json()["error"]["trace_id"]
    assert "<" not in trace and len(trace) <= 40
    assert r.headers["x-trace-id"] == trace


async def test_every_response_has_a_permissions_policy(client):
    r = await client.get("/v1/version")
    assert r.headers["permissions-policy"] == SECURITY_HEADERS["Permissions-Policy"]


async def test_a_conflict_says_what_happened_not_what_the_driver_said(db_client, admin_key):
    body = {"name": "dup", "scopes": ["fire"]}
    assert (await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key}, json=body)).status_code == 201
    r = await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key}, json=body)
    assert r.status_code == 409
    assert "one with the same name or key already exists" in r.json()["detail"]
    for leak in ("UNIQUE", "Duplicate", "api_keys", "1062"):
        assert leak not in r.text
