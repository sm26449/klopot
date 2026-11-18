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


async def test_validate_uses_the_rules_vars_extract_context(db_client, admin_key):
    """RL-02: the engine filters by vars_extract (plus what the expression
    reads); validate evaluates on that same context, not on the whole cache."""
    from app.core.state_cache import get_state_cache, reset_state_cache_for_tests
    reset_state_cache_for_tests()
    cache = get_state_cache()
    await cache.set("a.x", 5, source_kind="mqtt", stale_after_sec=300)
    await cache.set("b.y", 7, source_kind="mqtt", stale_after_sec=300)
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/validate",
                             json={"condition_expr": "a.x > 1", "vars_extract": ["b.y"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["result"] is True
    reset_state_cache_for_tests()


async def test_validate_does_not_report_string_contents_as_variables(db_client, admin_key):
    """RL-04: 'STATUS' is text, not a variable."""
    from app.core.state_cache import reset_state_cache_for_tests
    reset_state_cache_for_tests()
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules/validate",
                             json={"condition_expr": "contains(sms.body, 'STATUS') and var_age('a.b') < 9"}, headers=h)
    body = r.json()
    assert [v["name"] for v in body["referenced_vars"]] == ["sms.body", "a.b"]
    assert "STATUS" not in body["unknown_vars"]


async def test_a_rule_with_a_regex_re2_cannot_run_is_refused(db_client, admin_key):
    """RL-01: refused at save instead of matching nothing for ever."""
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/rules", headers=h, json={
        "name": "rl01_lookahead", "template_type": "t",
        "condition_expr": 'regex_match(a.s, "x(?!y)")',
    })
    assert r.status_code == 422 and "lookahead" in r.text
