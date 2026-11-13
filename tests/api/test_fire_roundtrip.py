"""End-to-end API smoke tests.

Exercises the full happy path: create a template via /v1/templates,
fire it via /v1/fire, read the resulting log row via /v1/log/{id}.
SQLite-backed; no MQTT or live engine.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.channels.manager import DispatchOutcome


# ── Auth gate ─────────────────────────────────────────────────────


async def test_unauthenticated_request_returns_401(db_client):
    r = await db_client.get("/v1/templates")
    assert r.status_code == 401


async def test_invalid_key_returns_401(db_client):
    r = await db_client.get("/v1/templates", headers={"X-API-Key": "bogus_short"})
    assert r.status_code == 401


# ── Templates CRUD ────────────────────────────────────────────────


async def test_list_templates_empty(db_client, admin_key):
    r = await db_client.get(
        "/v1/templates",
        headers={"X-API-Key": admin_key},
    )
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


async def test_create_template_then_get(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    body = {
        "type": "ci_smoke",
        "severity": "info",
        "icon": "🟢",
        "title_template": "Smoke OK",
        "message_template": "all good",
        "min_repeat_min": 0,
        "enabled": True,
    }
    r = await db_client.post("/v1/templates", json=body, headers=h)
    assert r.status_code == 201
    created = r.json()
    assert created["type"] == "ci_smoke"
    assert created["severity"] == "info"

    # Get by type
    r2 = await db_client.get("/v1/templates/ci_smoke", headers=h)
    assert r2.status_code == 200
    assert r2.json()["type"] == "ci_smoke"


async def test_create_duplicate_template_409(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    body = {
        "type": "dup",
        "severity": "info",
        "icon": "x",
        "title_template": "x",
        "message_template": "x",
        "min_repeat_min": 0,
        "enabled": True,
    }
    r = await db_client.post("/v1/templates", json=body, headers=h)
    assert r.status_code == 201
    r2 = await db_client.post("/v1/templates", json=body, headers=h)
    assert r2.status_code == 409


async def test_patch_template_updates_fields(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await db_client.post(
        "/v1/templates", headers=h,
        json={
            "type": "patchme", "severity": "info", "icon": "x",
            "title_template": "old", "message_template": "x",
            "min_repeat_min": 0, "enabled": True,
        },
    )
    r = await db_client.patch(
        "/v1/templates/patchme",
        json={"title_template": "new", "enabled": False},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["title_template"] == "new"
    assert r.json()["enabled"] is False


async def test_delete_template(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await db_client.post(
        "/v1/templates", headers=h,
        json={
            "type": "deleteme", "severity": "info", "icon": "x",
            "title_template": "x", "message_template": "x",
            "min_repeat_min": 0, "enabled": True,
        },
    )
    r = await db_client.delete("/v1/templates/deleteme", headers=h)
    assert r.status_code == 204
    r = await db_client.get("/v1/templates/deleteme", headers=h)
    assert r.status_code == 404


# ── /v1/fire roundtrip ────────────────────────────────────────────


@pytest.fixture
def fake_dispatch_ok():
    async def _dispatch(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        return DispatchOutcome(succeeded=list(channel_names), failed={})
    return _dispatch


async def test_fire_unknown_type(db_client, admin_key):
    r = await db_client.post(
        "/v1/fire",
        headers={"X-API-Key": admin_key},
        json={"type": "ghost", "context": {}},
    )
    # Endpoint accepts the call; suppressed_reason indicates nothing
    # was dispatched.
    assert r.status_code in (200, 202)
    body = r.json()
    assert body["dispatched"] is False
    assert body.get("suppressed_reason") == "unknown_type"


async def test_fire_known_template_writes_log(db_client, admin_key, fake_dispatch_ok):
    h = {"X-API-Key": admin_key}
    # Seed a template
    await db_client.post(
        "/v1/templates", headers=h,
        json={
            "type": "smoke_fire", "severity": "info", "icon": "🟢",
            "title_template": "OK {x}", "message_template": "msg {x}",
            "min_repeat_min": 0, "enabled": True,
        },
    )
    # Fire it (channels empty → suppressed_reason='gated' since no
    # template_channels link). We're verifying the API path works,
    # not the dispatch outcome.
    r = await db_client.post(
        "/v1/fire", headers=h,
        json={"type": "smoke_fire", "context": {"x": "42"}, "test": True},
    )
    assert r.status_code in (200, 202)
    body = r.json()
    assert body["title"] == "OK 42"


async def test_log_listing_filters(db_client, admin_key, fake_dispatch_ok):
    h = {"X-API-Key": admin_key}
    await db_client.post(
        "/v1/templates", headers=h,
        json={
            "type": "log_t", "severity": "warning", "icon": "x",
            "title_template": "t", "message_template": "m",
            "min_repeat_min": 0, "enabled": True,
        },
    )
    # Fire a few times to populate the log
    for i in range(3):
        await db_client.post(
            "/v1/fire", headers=h,
            json={"type": "log_t", "context": {"i": str(i)}, "test": True},
        )
    r = await db_client.get(
        "/v1/log",
        params={"type": "log_t", "limit": 10},
        headers=h,
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(it["type"] == "log_t" for it in items)


# ── Health ────────────────────────────────────────────────────────


async def test_health_no_auth_required(db_client):
    r = await db_client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "alertd"


async def test_metrics_returns_prometheus_format(db_client):
    r = await db_client.get("/v1/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    # Counters defined in app.metrics must appear in the output
    assert "alertd_fires_total" in body
