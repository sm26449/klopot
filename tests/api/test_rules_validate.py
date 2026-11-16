"""F3: POST /v1/rules/validate (parse + live-reference check)."""
from __future__ import annotations


async def test_validate_ok_with_reference(db_client, admin_key):
    from app.core.state_cache import get_state_cache, reset_state_cache_for_tests
    reset_state_cache_for_tests()
    await get_state_cache().set("soc", 42.0, source_kind="mqtt", stale_after_sec=300)

    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/validate",
                             json={"condition_expr": "soc < 20"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["result"] is False  # 42 < 20
    names = {v["name"]: v for v in body["referenced_vars"]}
    assert names["soc"]["present"] is True
    assert names["soc"]["live_value"] == 42.0
    assert body["unknown_vars"] == []
    reset_state_cache_for_tests()


async def test_validate_flags_unknown_var(db_client, admin_key):
    from app.core.state_cache import reset_state_cache_for_tests
    reset_state_cache_for_tests()
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/validate",
                             json={"condition_expr": "ghost_var > 5"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "ghost_var" in body["unknown_vars"]


async def test_validate_syntax_error(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/validate",
                             json={"condition_expr": "soc <"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]


async def test_validate_ignores_functions_as_vars(db_client, admin_key):
    from app.core.state_cache import reset_state_cache_for_tests
    reset_state_cache_for_tests()
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/validate",
                             json={"condition_expr": "var_age('soc') < 60"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    # var_age is a function call, not a referenced variable
    assert all(v["name"] != "var_age" for v in body["referenced_vars"])
    assert "var_age" not in body["unknown_vars"]
