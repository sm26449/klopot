"""Smoke tests for the health endpoint.

These run without any external dependencies (no DB, no MQTT). They
prove the FastAPI scaffolding boots and responds.
"""
from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_200(client: AsyncClient) -> None:
    """`GET /v1/health` always returns 200, even when components
    are not yet wired (they report 'unknown' instead of failing)."""
    response = await client.get("/v1/health")
    assert response.status_code == 200


async def test_health_payload_shape(client: AsyncClient) -> None:
    """Response body must match the documented shape so external
    callers (Prometheus blackbox exporter, uptime monitors) can rely
    on it."""
    response = await client.get("/v1/health")
    body = response.json()

    assert body["service"] == "alertd"
    assert "version" in body
    assert body["status"] in ("ok", "degraded", "down")

    # Components map: at least 'service' must be present and ok.
    components = body["components"]
    assert "service" in components
    assert components["service"]["status"] == "ok"

    # In a unit-test context (in-process FastAPI client, no DB
    # connection, no MQTT, no input adapters started), the database
    # and mqtt components legitimately report 'down' / 'unknown'.
    # We accept either — the contract is that the keys exist and
    # carry one of the documented statuses.
    assert components["database"]["status"] in ("ok", "down", "unknown")
    assert components["mqtt"]["status"] in ("ok", "down", "unknown")


async def test_openapi_schema_published(client: AsyncClient) -> None:
    """OpenAPI auto-doc must be reachable. Future automated clients
    depend on this contract."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "alertd"
    # The /v1/health route must be registered in the schema.
    assert "/v1/health" in schema["paths"]


async def test_docs_page_reachable(client: AsyncClient) -> None:
    """Swagger UI is served at /docs."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()
