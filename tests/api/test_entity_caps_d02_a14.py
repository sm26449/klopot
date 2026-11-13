"""D-02/A-14: NFR's entity caps (rules/inputs/channels) must be enforced at
create, not merely documented.

The caps are configurable (``ALERTD_MAX_RULES`` etc., defaulting to NFR's
100/50/20); a create — via REST or config import — that would push the total
past the limit is refused with 409 LIMIT_REACHED. Updates to existing rows are
never blocked, so an instance already over a (lowered) cap keeps working and can
re-import its own config; only genuinely new rows are gated. ``cap <= 0``
disables a limit.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1._crud import enforce_create_cap
from app.config import get_settings
from app.db.models import Channel, ChannelKind, Input, InputKind, Rule
from app.services import config_io

pytestmark = pytest.mark.anyio


@contextmanager
def _caps(*, rules=None, inputs=None, channels=None):
    s = get_settings()
    old = (s.max_rules, s.max_inputs, s.max_channels)
    if rules is not None:
        object.__setattr__(s, "max_rules", rules)
    if inputs is not None:
        object.__setattr__(s, "max_inputs", inputs)
    if channels is not None:
        object.__setattr__(s, "max_channels", channels)
    try:
        yield
    finally:
        object.__setattr__(s, "max_rules", old[0])
        object.__setattr__(s, "max_inputs", old[1])
        object.__setattr__(s, "max_channels", old[2])


# ── enforce_create_cap helper (covers all three models' wiring) ───────


async def test_enforce_cap_blocks_at_limit_and_passes_under(db_session, make_rule, make_template):
    db_session.add(make_template(type="t"))
    db_session.add_all([make_rule(template_type="t", name=f"r{i}") for i in range(3)])
    await db_session.commit()

    # 3 exist, cap 3 → a 4th is refused.
    with pytest.raises(HTTPException) as ei:
        await enforce_create_cap(db_session, Rule, 3, entity="Rule")
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "LIMIT_REACHED"
    assert ei.value.detail["limit"] == 3
    assert ei.value.detail["current"] == 3

    # cap 4 → one more is allowed; cap 0 → unlimited.
    await enforce_create_cap(db_session, Rule, 4, entity="Rule")
    await enforce_create_cap(db_session, Rule, 0, entity="Rule")


async def test_enforce_cap_is_generic_across_capped_models(db_session):
    """The same helper backs inputs and channels (the handlers call it with
    their own model), so it must count each model independently."""
    db_session.add(Input(name="in1", kind=InputKind.mqtt, config={"host": "x"}, enabled=False))
    db_session.add(Channel(name="ch1", kind=ChannelKind.ui, config={}))
    await db_session.commit()

    with pytest.raises(HTTPException) as ei:
        await enforce_create_cap(db_session, Input, 1, entity="Input")
    assert ei.value.detail["entity"] == "Input"
    with pytest.raises(HTTPException) as ej:
        await enforce_create_cap(db_session, Channel, 1, entity="Channel")
    assert ej.value.detail["entity"] == "Channel"
    # Under their own limits, both pass.
    await enforce_create_cap(db_session, Input, 2, entity="Input")
    await enforce_create_cap(db_session, Channel, 2, entity="Channel")


async def test_enforce_cap_counts_batch_n_new(db_session, make_rule, make_template):
    db_session.add(make_template(type="t"))
    db_session.add_all([make_rule(template_type="t", name=f"r{i}") for i in range(2)])
    await db_session.commit()
    # 2 exist, cap 4, importing 3 new → 2+3 > 4 → refused.
    with pytest.raises(HTTPException):
        await enforce_create_cap(db_session, Rule, 4, entity="Rule", n_new=3)
    # 2 new is fine.
    await enforce_create_cap(db_session, Rule, 4, entity="Rule", n_new=2)


# ── REST create path ──────────────────────────────────────────────────


async def test_rule_create_refused_at_cap(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    body = {"template_type": "t", "condition_expr": "True"}
    with _caps(rules=2):
        assert (await db_client.post("/v1/rules", json={**body, "name": "r1"}, headers=h)).status_code == 201
        assert (await db_client.post("/v1/rules", json={**body, "name": "r2"}, headers=h)).status_code == 201
        r = await db_client.post("/v1/rules", json={**body, "name": "r3"}, headers=h)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LIMIT_REACHED"


async def test_update_not_blocked_over_cap(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    with _caps(rules=1):
        created = await db_client.post(
            "/v1/rules",
            json={"name": "only", "template_type": "t", "condition_expr": "True"},
            headers=h,
        )
        assert created.status_code == 201
        rid = created.json()["id"]
        # An update to the existing rule is never gated, even at the cap.
        upd = await db_client.patch(f"/v1/rules/{rid}", json={"sort_order": 5}, headers=h)
    assert upd.status_code == 200


async def test_cap_zero_disables_enforcement(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    body = {"template_type": "t", "condition_expr": "True"}
    with _caps(rules=0):
        for i in range(3):
            r = await db_client.post("/v1/rules", json={**body, "name": f"z{i}"}, headers=h)
            assert r.status_code == 201


# ── config import path ────────────────────────────────────────────────


async def test_import_refuses_new_rows_over_cap(db_session):
    pack = {"rules": [
        {"name": "a", "template_type": "t", "condition_expr": "True"},
        {"name": "b", "template_type": "t", "condition_expr": "True"},
    ]}
    with _caps(rules=1):
        plan = await config_io.import_config(db_session, pack, apply=True)
    assert not plan.ok
    assert any("limit of 1" in e for e in plan.errors)


async def test_import_pure_updates_over_cap_allowed(db_session, make_rule, make_template):
    # Seed 2 rules while the cap is high, then re-import them as updates under a
    # cap of 1: no new rows, so the import still applies.
    db_session.add(make_template(type="t"))
    db_session.add_all([
        make_rule(template_type="t", name="a", condition_expr="True"),
        make_rule(template_type="t", name="b", condition_expr="True"),
    ])
    await db_session.commit()

    pack = {"rules": [
        {"name": "a", "template_type": "t", "condition_expr": "x > 1"},
        {"name": "b", "template_type": "t", "condition_expr": "x > 2"},
    ]}
    with _caps(rules=1):
        plan = await config_io.import_config(db_session, pack, apply=True)
    assert plan.ok, plan.errors
    await db_session.commit()
    updated = (await db_session.execute(
        select(Rule.condition_expr).where(Rule.name == "a")
    )).scalar_one()
    assert updated == "x > 1"
