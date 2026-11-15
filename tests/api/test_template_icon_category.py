"""Template icon validation and category canonicalisation.

Production had mojibake icons (``âš¡``, ``ðŸš¨``), a lost one (``??``) and
the categories ``grid`` / ``Grid`` side by side (2026-11-14).
"""
from __future__ import annotations

import pytest

from app.utils.icons import normalize_category, validate_icon

GOOD = ["🚀", "⚠️", "☀️", "🌡️", "👨‍🔧", "🇷🇴", " 🔋 "]
BAD = ["âš¡", "ðŸš¨", "ðŸ”’", "??", "x", "1", "⚡x", "-"]


@pytest.mark.parametrize("icon", GOOD)
def test_valid_emoji_pass(icon):
    assert validate_icon(icon) == icon.strip()


@pytest.mark.parametrize("icon", BAD)
def test_text_and_mojibake_rejected(icon):
    with pytest.raises(ValueError, match="emoji"):
        validate_icon(icon)


@pytest.mark.parametrize(("raw", "expected"), [(None, None), ("", None), ("   ", None), ("  DG   controller ", "DG controller")])
def test_category_whitespace_normalised(raw, expected):
    assert normalize_category(raw) == expected
    assert validate_icon("") is None


def _tpl(type_, **kw):
    return {"type": type_, "severity": "info", "title_template": "t", **kw}


async def test_api_rejects_mojibake_icon(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/templates", json=_tpl("bad_icon", icon="âš¡"), headers=h)
    assert r.status_code == 422
    assert "emoji" in r.text
    r = await db_client.post("/v1/templates", json=_tpl("good_icon", icon="⚡"), headers=h)
    assert r.status_code == 201, r.text
    r = await db_client.patch("/v1/templates/good_icon", json={"icon": "??"}, headers=h)
    assert r.status_code == 422
    r = await db_client.patch("/v1/templates/good_icon", json={"icon": ""}, headers=h)
    assert r.status_code == 200 and r.json()["icon"] is None


async def test_api_reuses_existing_category_spelling(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    for i in range(2):
        assert (await db_client.post("/v1/templates", json=_tpl(f"g{i}", category="Grid"), headers=h)).status_code == 201
    r = await db_client.post("/v1/templates", json=_tpl("g_lower", category="  grid "), headers=h)
    assert r.json()["category"] == "Grid"
    r = await db_client.patch("/v1/templates/g_lower", json={"category": "GRID"}, headers=h)
    assert r.json()["category"] == "Grid"
    r = await db_client.post("/v1/templates", json=_tpl("brand_new", category="Weather"), headers=h)
    assert r.json()["category"] == "Weather"


async def test_import_rejects_mojibake_icon(db_client, admin_key):
    pack = "templates:\n  - type: imp_bad\n    severity: info\n    title_template: t\n    icon: \"ðŸš¨\"\n"
    r = await db_client.post(
        "/v1/config/validate", content=pack,
        headers={"X-API-Key": admin_key, "Content-Type": "application/yaml"},
    )
    assert r.status_code in (200, 422)
    body = r.json()
    errors = body.get("errors") or body.get("detail", {}).get("errors") or [str(body)]
    assert any("emoji" in str(e) for e in errors), body


def test_icon_parity_fixture_is_the_server_rule():
    """tests/js/support/icon_parity.json: the admin UI's isValidIcon must give
    these verdicts (tests/js/icon_picker.test.mjs); they are the server's."""
    import json
    from pathlib import Path

    from app.utils.icons import validate_icon

    def ok(icon):
        try:
            validate_icon(icon)
        except ValueError:
            return False
        return True

    fixture = Path(__file__).resolve().parents[1] / "js" / "support" / "icon_parity.json"
    cases = json.loads(fixture.read_text())
    assert {c["icon"]: c["valid"] for c in cases} == {c["icon"]: ok(c["icon"]) for c in cases}
    assert any(c["valid"] for c in cases) and any(not c["valid"] for c in cases)
