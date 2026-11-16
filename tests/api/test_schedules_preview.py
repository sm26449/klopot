"""F3: GET /v1/schedules/preview."""
from __future__ import annotations


async def test_preview_returns_n_times(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/schedules/preview", params={"cron": "0 21 * * *", "n": 3}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["next"]) == 3
    assert body["tz"]
    # Strictly increasing ISO timestamps
    assert body["next"] == sorted(body["next"])


async def test_preview_invalid_cron_422(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/schedules/preview", params={"cron": "not a cron"}, headers=h)
    assert r.status_code == 422


async def test_preview_default_n(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/schedules/preview", params={"cron": "*/5 * * * *"}, headers=h)
    assert r.status_code == 200
    assert len(r.json()["next"]) == 5


async def test_preview_does_not_shadow_get_by_id(db_client, admin_key):
    """`/schedules/preview` must not be captured by `/schedules/{id}`."""
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/schedules/preview", params={"cron": "0 0 * * *"}, headers=h)
    assert r.status_code == 200
