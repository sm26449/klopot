"""B-01: deleting an input that a variable references must be refused at the
DB boundary (ON DELETE RESTRICT), not cascade the child binding to NULL.

F11 already covers the ordinary pre-check 409 path. These tests cover the race
the pre-check cannot win on its own: a variable bound to the input *after* the
pre-check but *before* the delete commits. The RESTRICT FK refuses the delete
regardless of timing, and the handler surfaces that as the same 409 instead of
silently nulling (and thus trust-widening) the fresh binding.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import app.api.v1.inputs as inputs_mod
from app.auth import Actor
from app.db.models import Input, InputKind, Variable, VariableSource
from tests._db import fresh


async def _mk_bound(db_session) -> int:
    inp = Input(name="trusted", kind=InputKind.mqtt, config={"host": "x"}, enabled=False)
    db_session.add(inp)
    await db_session.commit()
    await db_session.refresh(inp)
    db_session.add(Variable(
        name="sensor", source=VariableSource.mqtt, input_id=inp.id,
        config={"topic": "reading", "type": "number"}, enabled=True,
    ))
    await db_session.commit()
    return inp.id


async def test_fk_restrict_refuses_delete_at_db_boundary(db_session):
    """The core fix: the DB itself refuses to delete a referenced input, and
    the binding is preserved (negative control: with SET NULL the delete
    succeeds and input_id becomes NULL)."""
    iid = await _mk_bound(db_session)
    inp = await db_session.get(Input, iid)

    with pytest.raises(IntegrityError):
        await db_session.delete(inp)
        await db_session.commit()
    await db_session.rollback()

    # Binding survived — not widened to accept-any.
    bound = (await db_session.execute(
        select(Variable.input_id).where(Variable.name == "sensor")
    )).scalar_one()
    assert bound == iid


async def test_delete_handler_translates_commit_race_to_409(db_session, monkeypatch):
    """The race path through the handler: the pre-check misses the concurrent
    insert (first lookup returns none), the commit hits RESTRICT, and the
    handler reports INPUT_IN_USE rather than leaking a raw FK error or
    deleting the input."""
    iid = await _mk_bound(db_session)

    real = inputs_mod._bound_variable_names
    calls = {"n": 0}

    async def racing_lookup(session, input_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return []  # pre-check: the concurrent insert is not yet visible
        return await real(session, input_id)  # commit failed; re-query sees it

    monkeypatch.setattr(inputs_mod, "_bound_variable_names", racing_lookup)
    admin = Actor(kind="api_key", id=1, name="admin", scopes=frozenset({"admin"}))

    with pytest.raises(HTTPException) as ei:
        await inputs_mod.delete_input(iid, session=db_session, actor=admin)
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "INPUT_IN_USE"
    assert "sensor" in ei.value.detail["variables"]

    # Input was NOT deleted.
    await fresh(db_session)
    assert await db_session.get(Input, iid) is not None
