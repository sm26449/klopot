"""F40: a cross-origin API-key client must be able to preflight a routing
PUT (PUT /v1/templates/{type}/channels)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings

pytestmark = pytest.mark.anyio


async def test_cors_preflight_allows_put(monkeypatch):
    monkeypatch.setenv("ALERTD_CORS_ORIGINS", "https://ui.example")
    get_settings.cache_clear()
    try:
        from app.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            r = await c.options(
                "/v1/templates/some_type/channels",
                headers={
                    "Origin": "https://ui.example",
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "X-API-Key",
                },
            )
        assert r.status_code in (200, 204), r.text
        assert "PUT" in r.headers.get("access-control-allow-methods", "")
    finally:
        monkeypatch.delenv("ALERTD_CORS_ORIGINS", raising=False)
        get_settings.cache_clear()
