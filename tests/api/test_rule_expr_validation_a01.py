"""A-01: the AST allowlist is applied at every write surface, not only at
eval time — rule create/update (REST), config import, computed-variable
formulas, and the validate endpoint — so a dangerous expression is refused
before it is ever stored.
"""
from __future__ import annotations

import pytest

from app.core.manager import VariableConfigError, dry_compile_variable
from app.db.models import VariableSource
from app.services import config_io

_BAD = '"a".rjust(5000000)'
_GOOD = "soc < 20"


async def test_create_rule_rejects_dangerous_expression(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post(
        "/v1/rules",
        json={"name": "bad", "template_type": "t", "condition_expr": _BAD},
        headers=h,
    )
    assert r.status_code == 422
    assert "invalid expression" in str(r.json()["detail"]).lower()


async def test_create_rule_accepts_valid_expression(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post(
        "/v1/rules",
        json={"name": "good", "template_type": "t", "condition_expr": _GOOD},
        headers=h,
    )
    assert r.status_code == 201


async def test_update_rule_rejects_dangerous_expression(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    created = await db_client.post(
        "/v1/rules",
        json={"name": "upd", "template_type": "t", "condition_expr": _GOOD},
        headers=h,
    )
    rid = created.json()["id"]
    r = await db_client.patch(f"/v1/rules/{rid}", json={"condition_expr": _BAD}, headers=h)
    assert r.status_code == 422


async def test_validate_endpoint_reports_rejection(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/validate", json={"condition_expr": _BAD}, headers=h)
    assert r.status_code == 200          # validate never 500s; it reports
    body = r.json()
    assert body["ok"] is False
    assert body["error"]


async def test_import_rejects_dangerous_rule_expression(db_session):
    pack = {"rules": [{"name": "x", "template_type": "t", "condition_expr": _BAD}]}
    plan = await config_io.import_config(db_session, pack, apply=True)
    assert not plan.ok
    assert any("invalid expression" in e for e in plan.errors)


async def test_import_allows_valid_rule_expression(db_session):
    pack = {"rules": [{"name": "y", "template_type": "t", "condition_expr": _GOOD}]}
    plan = await config_io.import_config(db_session, pack, apply=True)
    assert plan.ok, plan.errors


def test_computed_variable_formula_rejected():
    """Computed-variable formulas go through the same validator at write time."""
    with pytest.raises(VariableConfigError):
        dry_compile_variable(
            VariableSource.computed, {"formula": _BAD, "value_type": "number"}, "v"
        )
    # A valid formula compiles.
    dry_compile_variable(
        VariableSource.computed, {"formula": "a + b", "value_type": "number"}, "v"
    )
