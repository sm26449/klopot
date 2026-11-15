"""Rule eval_status: one definition for the badge, the banner and the filter.

``error``   — the expression fails (counted, may auto-disable);
``no_data`` — waiting for an input that has no value (not counted);
``ok``      — neither.
"""
from __future__ import annotations

import pytest

from app.schemas.rule import eval_status_of


@pytest.mark.parametrize(("count", "text", "expected"), [
    (0, None, "ok"),
    (0, "missing input: grid.cc_power_w (TypeError: …)", "no_data"),
    (3, "missing input: grid.cc_power_w (TypeError: …)", "error"),
    (2, "NameError: 'device' is not defined", "error"),
    (0, "NameError: 'device' is not defined", "error"),   # last real error, counter reset by a restart
])
def test_eval_status_of(count, text, expected):
    assert eval_status_of(count, text) == expected


@pytest.fixture
async def rules(db_session, make_rule, make_template):
    db_session.add(make_template(type="test_type"))
    db_session.add_all([
        make_rule(name="healthy"),
        make_rule(name="waiting", last_eval_error="missing input: sensor.x (TypeError: x)"),
        make_rule(name="broken", consecutive_eval_errors=4, last_eval_error="NameError: nope"),
        make_rule(name="old_error", last_eval_error="SyntaxError: bad"),
    ])
    await db_session.commit()


async def _names(client, key, **query):
    r = await client.get("/v1/rules", params=query, headers={"X-API-Key": key})
    assert r.status_code == 200, r.text
    return {i["name"]: i["eval_status"] for i in r.json()["items"]}


async def test_list_exposes_eval_status(db_client, admin_key, rules):
    assert await _names(db_client, admin_key) == {
        "healthy": "ok", "waiting": "no_data", "broken": "error", "old_error": "error",
    }


@pytest.mark.parametrize(("status", "expected"), [
    ("ok", {"healthy"}),
    ("no_data", {"waiting"}),
    ("error", {"broken", "old_error"}),
])
async def test_filter_by_eval_status(db_client, admin_key, rules, status, expected):
    assert set(await _names(db_client, admin_key, eval_status=status)) == expected


async def test_has_error_matches_the_error_status(db_client, admin_key, rules):
    assert set(await _names(db_client, admin_key, has_error="true")) == {"broken", "old_error"}
    assert set(await _names(db_client, admin_key, has_error="false")) == {"healthy", "waiting"}
