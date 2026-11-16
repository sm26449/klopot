"""V09: a reload-breaking variable config must be rejected before it is
committed, not persisted-then-500'd on the hot reload."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Variable


async def test_bad_variable_config_committed_before_reload_failure(db_client, admin_key):
    """POST an mqtt variable whose ``config.topic`` is a JSON object instead of
    a string. The topic is unhashable, so building the resolver's topic index on
    the next hot reload raises — the audited endpoint committed the row first
    and only then 500'd on the reload, leaving a persisted config that breaks
    every future reload. The fix dry-compiles the config first and rejects it
    with a 422, writing nothing."""
    h = {"X-API-Key": admin_key}
    body = {
        "name": "bad_topic_var",
        "source": "mqtt",
        "config": {"topic": {"not": "a string"}},
    }
    r = await db_client.post("/v1/variables", json=body, headers=h)

    # Rejected cleanly, not a 500 after a partial commit.
    assert r.status_code == 422, r.text

    # And nothing was persisted — a later reload can't be poisoned by it.
    from app.db import session as session_module
    async with session_module._session_factory() as s:
        found = (
            await s.execute(select(Variable).where(Variable.name == "bad_topic_var"))
        ).scalar_one_or_none()
    assert found is None


async def test_good_variable_config_still_accepted(db_client, admin_key):
    """A well-formed mqtt topic (a string) is unaffected by the guard."""
    h = {"X-API-Key": admin_key}
    body = {
        "name": "good_topic_var",
        "source": "mqtt",
        "config": {"topic": "plcbus/inverter/power"},
    }
    r = await db_client.post("/v1/variables", json=body, headers=h)
    assert r.status_code == 201, r.text
