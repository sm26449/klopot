"""The inbound webhook says nothing, and keeps nothing, before the token (review K10).

``POST /v1/inputs/{id}/webhook`` is anonymous. It answered 400 ``Input <name>
is kind=…`` and 503 ``Adapter for input <name> not running`` before checking
the token, so input ids, names and kinds could be enumerated. The activity log
dropped the body only on 401/403/404, so those answers — and FastAPI's 422 for
a non-numeric id — kept up to 64 KiB of an anonymous body for the retention
period. Now: a generic 404 for anything that is not a webhook-kind input, the
token next, and a body is stored only for a caller the endpoint let in.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.activity import get_activity_writer
from app.db.models import ApiRequest

pytestmark = pytest.mark.anyio

PAYLOAD = {"probe": "Z" * 3000}


def _h(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


async def _bodies(db_session) -> dict[tuple[str, int], str | None]:
    await get_activity_writer().flush()
    rows = (await db_session.execute(select(ApiRequest).where(ApiRequest.method == "POST"))).scalars().all()
    return {(r.path, r.status): r.request_body for r in rows}


async def _input(db_client, admin_key, **body) -> dict:
    r = await db_client.post("/v1/inputs", headers=_h(admin_key), json=body)
    assert r.status_code == 201, r.text[:200]
    return r.json()


async def test_anonymous_callers_learn_nothing_and_leave_no_body(db_client, admin_key, db_session):
    poller = await _input(db_client, admin_key, name="secret_poller", kind="http_poll",
                          config={"url": "https://example.com", "interval_sec": 60})
    paused = await _input(db_client, admin_key, name="paused_hook", kind="webhook", enabled=False,
                          config={"auth_required": True, "auth_token": "right-token-123456"})

    non_numeric = await db_client.post("/v1/inputs/abc/webhook", json=PAYLOAD)
    other_kind = await db_client.post(f"/v1/inputs/{poller['id']}/webhook", json=PAYLOAD)
    missing = await db_client.post("/v1/inputs/999999/webhook", json=PAYLOAD)
    not_running = await db_client.post(f"/v1/inputs/{paused['id']}/webhook", json=PAYLOAD)

    assert non_numeric.status_code == 422
    assert other_kind.status_code == 404
    assert other_kind.json() == missing.json(), "a non-webhook input must look like a missing one"
    assert "secret_poller" not in other_kind.text
    # A disabled input is not there: the same answer as an id that does not
    # exist, whatever the token (public-exposure review).
    assert not_running.status_code == 404
    assert not_running.json() == missing.json()
    assert "paused_hook" not in not_running.text

    stored = await _bodies(db_session)
    anonymous = {k: v for k, v in stored.items() if k[0].endswith("/webhook")}
    assert len(anonymous) == 4, anonymous.keys()
    assert all(body is None for body in anonymous.values()), [k for k, v in anonymous.items() if v]


async def test_a_caller_with_the_token_is_still_recorded(db_client, admin_key, db_session):
    hook = await _input(db_client, admin_key, name="open_hook", kind="webhook",
                        config={"auth_required": True, "auth_token": "right-token-123456"})
    r = await db_client.post(f"/v1/inputs/{hook['id']}/webhook", json=PAYLOAD,
                             headers={"X-Input-Token": "right-token-123456"})
    assert r.status_code == 202, r.text[:200]
    stored = await _bodies(db_session)
    assert "ZZZZ" in (stored[(f"/v1/inputs/{hook['id']}/webhook", 202)] or "")
