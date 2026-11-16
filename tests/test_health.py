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


async def test_an_anonymous_caller_gets_the_status_only(client: AsyncClient) -> None:
    """Uptime monitors need the status; the components name hosts, inputs
    and error texts, and the version says what to attack (review F7, F13)."""
    body = (await client.get("/v1/health")).json()
    assert set(body) == {"status", "service"}
    assert body["status"] in ("ok", "degraded", "down")


async def test_the_details_need_read(db_client: AsyncClient, admin_key: str) -> None:
    """The real credential path: a key with ``read`` sees the components, a
    ``fire``-only key the status, a wrong key 401 (counted, as anywhere)."""
    async def key(scopes: list[str]) -> str:
        r = await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key},
                                 json={"name": f"k_{'_'.join(scopes)}", "scopes": scopes})
        return r.json()["key"]

    reader, firer = await key(["read"]), await key(["fire"])
    assert "components" in (await db_client.get("/v1/health", headers={"X-API-Key": reader})).json()
    assert set((await db_client.get("/v1/health", headers={"X-API-Key": firer})).json()) == {"status", "service"}
    assert (await db_client.get("/v1/health", headers={"X-API-Key": "alertd_" + "x" * 43})).status_code == 401


async def test_health_payload_shape(read_client: AsyncClient) -> None:
    """Response body must match the documented shape so external
    callers with ``read`` (pv-stack-ui, dashboards) can rely on it."""
    response = await read_client.get("/v1/health")
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


# Every code a component can report; the admin UI translates each one
# (i18n `health.detail.<code>`), so a new code needs a string there too.
HEALTH_CODES = {
    "timezone", "db_ok", "db_error", "task_running", "task_stopped",
    "outbox_clear", "outbox_overdue", "outbox_probe_unavailable",
    "inputs_none", "inputs_optional_only", "inputs_connected", "inputs_partial", "inputs_down",
}


async def test_health_components_carry_translatable_codes(read_client: AsyncClient) -> None:
    """Each component names its detail with a stable `code` + `params`, so
    the UI can show it in the operator's language; `detail` stays English."""
    components = (await read_client.get("/v1/health")).json()["components"]
    for name, comp in components.items():
        assert comp["code"] in HEALTH_CODES, name
        assert isinstance(comp["params"], dict), name
    assert components["service"]["params"]["tz"]
    assert components["mqtt"]["code"] == "inputs_none"  # nothing declared in the test app


def test_every_health_code_has_ui_strings() -> None:
    """en.js and ro.js define a string for every health code."""
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "app" / "admin_ui" / "static" / "i18n"
    for lang in ("en", "ro"):
        source = (static / f"{lang}.js").read_text(encoding="utf-8")
        block = source.split("healthDetail: {", 1)[1].split("},", 1)[0]
        missing = [c for c in HEALTH_CODES if f"{c}:" not in block]
        assert not missing, (lang, missing)
