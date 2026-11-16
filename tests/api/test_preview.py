"""F3: POST /v1/templates/{type}/preview."""
from __future__ import annotations


async def _mk_template(client, h):
    r = await client.post("/v1/templates", json={
        "type": "soc_low", "severity": "warning",
        "title_template": "SOC {soc}%",
        "message_template": "Battery {name} at {soc}% (limit {limit})",
    }, headers=h)
    assert r.status_code == 201, r.text


async def test_preview_renders_and_reports_missing(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    r = await db_client.post("/v1/templates/soc_low/preview", json={
        "context": {"soc": 18, "name": "pack1"},
    }, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "SOC 18%"
    assert "pack1" in body["message"]
    assert body["missing_vars"] == ["limit"]


async def test_preview_accepts_bare_context(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    r = await db_client.post("/v1/templates/soc_low/preview",
                             json={"soc": 50, "name": "p", "limit": 20}, headers=h)
    assert r.status_code == 200
    assert r.json()["missing_vars"] == []


async def test_preview_empty_body_all_missing(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await _mk_template(db_client, h)
    r = await db_client.post("/v1/templates/soc_low/preview", json={}, headers=h)
    assert r.status_code == 200
    assert set(r.json()["missing_vars"]) == {"soc", "name", "limit"}


async def test_preview_unknown_template_404(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/templates/nope/preview", json={}, headers=h)
    assert r.status_code == 404
