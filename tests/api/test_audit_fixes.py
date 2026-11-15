"""Regression tests for audit 2026-11-07 fixes.

- A20: internal/SQL exceptions must not leak to the client (generic
  message + trace_id); ``/v1/log/stats?window=`` must not 500 on a huge
  or non-positive amount.
- A08: secret masking must reach NESTED values (webhook ``headers``),
  on both the API read path and the masked config export.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.secrets_registry import MASK

pytestmark = pytest.mark.anyio

WEBHOOK_SECRET = "Bearer super-secret-token-xyz"


# ── A20: no internal leakage, bounded window ───────────────────────


async def test_unhandled_exception_is_generic_with_trace(db_engine, admin_key):
    # A dedicated client that does NOT re-raise app exceptions, so we can
    # inspect the 500 the exception handler produces (the conftest
    # db_client uses raise_app_exceptions=True).
    from app.main import create_app
    transport = ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        h = {"X-API-Key": admin_key}
        # Force a non-HTTP exception inside the stats handler.
        with patch("app.api.v1.log._parse_window", side_effect=ValueError("SELECT secret_sql_detail FROM x")):
            r = await client.get("/v1/log/stats", params={"window": "24h"}, headers=h)
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["message"] == "Internal server error"
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["trace_id"]
    assert r.headers.get("X-Trace-Id") == body["error"]["trace_id"]
    # The raw exception text must NOT reach the client.
    assert "secret_sql_detail" not in r.text
    assert "SELECT" not in r.text


async def test_log_stats_window_bounds(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    assert (await db_client.get("/v1/log/stats", params={"window": "24h"}, headers=h)).status_code == 200
    # Previously 500 (timedelta OverflowError) — now a clean 422.
    assert (await db_client.get("/v1/log/stats", params={"window": "9" * 40 + "d"}, headers=h)).status_code == 422
    assert (await db_client.get("/v1/log/stats", params={"window": "0h"}, headers=h)).status_code == 422
    assert (await db_client.get("/v1/log/stats", params={"window": "nope"}, headers=h)).status_code == 422


# ── A08: nested secret masking (webhook headers) ───────────────────


async def test_channel_read_masks_nested_header_secret(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={
        "name": "wh_nested", "kind": "webhook",
        "config": {
            "url": "https://example.test/hook/visible-destination",
            "headers": {"Authorization": WEBHOOK_SECRET, "X-Trace": "ok"},
            "auth_value": "another-secret",
        },
    }, headers=h)
    assert r.status_code == 201, r.text
    cfg = r.json()["config"]
    assert cfg["headers"]["Authorization"] == MASK          # nested secret masked
    assert cfg["headers"]["X-Trace"] == "ok"                # non-secret nested kept
    assert cfg["auth_value"] == MASK                        # registered secret masked
    # A-06: the destination path can itself be a credential (Slack/Discord
    # style), so only the safe scheme+host is shown, the path collapsed.
    assert cfg["url"] == "https://example.test/…"
    assert "visible-destination" not in cfg["url"]
    assert WEBHOOK_SECRET not in r.text

    cid = r.json()["id"]
    r = await db_client.get(f"/v1/channels/{cid}", headers=h)
    assert WEBHOOK_SECRET not in r.text


async def test_masked_export_redacts_nested_header(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await db_client.post("/v1/channels", json={
        "name": "wh_export", "kind": "webhook",
        "config": {"url": "https://x.test/h", "headers": {"Authorization": WEBHOOK_SECRET}},
    }, headers=h)
    r = await db_client.get("/v1/config/export", params={"mask_secrets": "true"}, headers=h)
    assert r.status_code == 200, r.text
    assert WEBHOOK_SECRET not in r.text   # not leaked in the "masked" export


# ── A10: cron import recomputes next_fire_at ───────────────────────


async def _import(client, h, yaml_text):
    return await client.post(
        "/v1/config/import", params={"apply": "true"},
        content=yaml_text, headers={**h, "Content-Type": "application/yaml"},
    )


async def _schedule_next(client, h, name):
    p = await client.get("/v1/schedules", headers=h)
    row = next(s for s in p.json()["items"] if s["name"] == name)
    return row["next_fire_at"]


async def test_cron_import_recomputes_next_fire(db_client, admin_key):
    from datetime import datetime

    h = {"X-API-Key": admin_key}
    base = (
        "templates:\n"
        "  - type: a10_sched\n"
        "    severity: info\n"
        "    title_template: hi\n"
        "schedules:\n"
        "  - name: a10_test\n"
        "    cron_expr: \"0 0 1 1 *\"\n"   # once a year — next fire far away
        "    template_type: a10_sched\n"
        "    enabled: true\n"
    )
    r = await _import(db_client, h, base)
    assert r.status_code == 200 and r.json().get("applied"), r.text
    far = await _schedule_next(db_client, h, "a10_test")
    assert far is not None

    # Re-import with a frequent cron; next_fire_at MUST be recomputed soon,
    # not left at the yearly time (audit A10).
    changed = base.replace('"0 0 1 1 *"', '"*/5 * * * *"')
    r = await _import(db_client, h, changed)
    assert r.status_code == 200 and r.json().get("applied"), r.text
    soon = await _schedule_next(db_client, h, "a10_test")

    assert soon != far, "next_fire_at was not recomputed"
    delta = datetime.fromisoformat(soon.replace("Z", "")) - datetime.utcnow()
    assert delta.total_seconds() < 6 * 60, f"expected within ~5 min, got {soon}"


# ── A09: YAML import validates before writing (no 500 on bad input) ──


async def _validate(client, h, yaml_text):
    return await client.post(
        "/v1/config/validate",
        content=yaml_text, headers={**h, "Content-Type": "application/yaml"},
    )


async def test_import_scalar_section_is_localized_error_not_500(db_client, admin_key):
    # `inputs: 5` used to crash the cross-ref loop (TypeError) → 500.
    r = await _validate(db_client, {"X-API-Key": admin_key}, "inputs: 5\n")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert any("inputs" in e for e in body["errors"])


async def test_import_invalid_channel_kind_is_localized_error_not_500(db_client, admin_key):
    yaml_text = "channels:\n  - name: c\n    kind: carrier_pigeon\n"
    r = await _validate(db_client, {"X-API-Key": admin_key}, yaml_text)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert any("kind" in e.lower() for e in body["errors"])


async def test_import_template_without_title_is_localized_error_not_500(db_client, admin_key):
    yaml_text = "templates:\n  - type: t\n    severity: info\n"
    r = await _validate(db_client, {"X-API-Key": admin_key}, yaml_text)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert any("title_template" in e for e in body["errors"])


async def test_import_settings_unknown_key_rejected(db_client, admin_key):
    # `settings: {id: 2}` was "declared valid" and would setattr the PK.
    r = await _validate(db_client, {"X-API-Key": admin_key}, "settings:\n  id: 2\n")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert any("settings" in e and "id" in e for e in body["errors"])


async def test_import_duplicate_name_in_pack_rejected(db_client, admin_key):
    yaml_text = (
        "inputs:\n"
        "  - name: dup\n    kind: mqtt\n"
        "  - name: dup\n    kind: mqtt\n"
    )
    r = await _validate(db_client, {"X-API-Key": admin_key}, yaml_text)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert any("duplicate" in e.lower() for e in body["errors"])


async def test_invalid_import_writes_nothing(db_client, admin_key):
    # A bad pack must not partially apply, even with apply=true.
    h = {"X-API-Key": admin_key}
    yaml_text = (
        "inputs:\n  - name: good_input\n    kind: mqtt\n"      # valid row …
        "templates:\n  - type: t\n    severity: info\n"        # … invalid row (no title)
    )
    r = await db_client.post(
        "/v1/config/import", params={"apply": "true"},
        content=yaml_text, headers={**h, "Content-Type": "application/yaml"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False
    # The valid input in the same pack must NOT have been written.
    inputs = (await db_client.get("/v1/inputs", headers=h)).json()["items"]
    assert not any(i["name"] == "good_input" for i in inputs)


async def test_valid_export_round_trips_through_validation(db_client, admin_key):
    # Apply a minimal valid pack, export it, then re-validate the exported
    # YAML — the new contract must accept what we emit (no regression).
    h = {"X-API-Key": admin_key}
    yaml_text = (
        "templates:\n  - type: rt_tmpl\n    severity: warning\n    title_template: hi\n"
        "channels:\n  - name: rt_ui\n    kind: ui\n"
        "routes:\n  - template: rt_tmpl\n    channel: rt_ui\n    severity_min: info\n"
    )
    r = await db_client.post(
        "/v1/config/import", params={"apply": "true"},
        content=yaml_text, headers={**h, "Content-Type": "application/yaml"},
    )
    assert r.status_code == 200 and r.json().get("applied"), r.text

    exported = (await db_client.get("/v1/config/export", headers=h)).text
    r2 = await _validate(db_client, h, exported)
    assert r2.status_code == 200, r2.text
    assert r2.json()["ok"] is True, r2.json().get("errors")


# ── A35: config.import audit + trace correlation ──────────────────


async def test_config_import_writes_audit_entry(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    yaml_text = (
        "templates:\n  - type: a35_tmpl\n    severity: info\n    title_template: hi\n"
    )
    r = await db_client.post(
        "/v1/config/import", params={"apply": "true"},
        content=yaml_text, headers={**h, "Content-Type": "application/yaml"},
    )
    assert r.status_code == 200 and r.json().get("applied"), r.text

    audit = (await db_client.get("/v1/audit", params={"action": "config.import"}, headers=h)).json()
    assert audit["total"] >= 1
    entry = audit["items"][0]
    assert entry["action"] == "config.import"
    assert entry["resource_kind"] == "config"
    # Redacted summary: counts/names only, no raw secret values.
    assert "a35_tmpl" in str(entry.get("after"))


async def test_record_change_fills_trace_id_from_contextvar(db_engine, db_session):
    from sqlalchemy import select

    from app.audit import record_change
    from app.auth import Actor
    from app.db.models import AuditLog
    from app.logging_setup import trace_id_var

    actor = Actor(kind="api_key", id=1, name="t", scopes=frozenset({"admin"}))
    token = trace_id_var.set("trace_xyz789")
    try:
        await record_change(db_session, actor, "test.action", resource_kind="x")
        await db_session.commit()
    finally:
        trace_id_var.reset(token)

    row = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "test.action")
        )
    ).scalars().one()
    assert row.trace_id == "trace_xyz789"
