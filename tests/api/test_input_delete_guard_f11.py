"""F11: deleting an input that variables still reference must be refused,
not silently widen a bound variable into an unbound (accept-any) one."""
from __future__ import annotations

from app.db.models import Input, InputKind, Variable, VariableSource


async def _mk_input(db_session, name="trusted", enabled=False) -> int:
    inp = Input(name=name, kind=InputKind.mqtt, config={"host": "x"}, enabled=enabled)
    db_session.add(inp)
    await db_session.commit()
    await db_session.refresh(inp)
    return inp.id


async def test_delete_input_bound_by_variable_is_409(db_client, admin_key, db_session):
    iid = await _mk_input(db_session)
    db_session.add(Variable(
        name="sensor", source=VariableSource.mqtt, input_id=iid,
        config={"topic": "reading", "type": "number"}, enabled=True,
    ))
    await db_session.commit()

    r = await db_client.delete(f"/v1/inputs/{iid}", headers={"X-API-Key": admin_key})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "INPUT_IN_USE"
    assert "sensor" in detail["variables"]


async def test_delete_unbound_input_succeeds(db_client, admin_key, db_session):
    iid = await _mk_input(db_session, name="lonely")
    r = await db_client.delete(f"/v1/inputs/{iid}", headers={"X-API-Key": admin_key})
    assert r.status_code == 204, r.text
