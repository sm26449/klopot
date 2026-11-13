"""A-06: a credential-bearing destination URL (webhook ``url``, sms
``gateway_url``) must not leak through read / export / audit. It is shown
as a safe ``scheme://host/…`` display; a client that echoes that display
back on write must not overwrite the stored URL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Channel
from app.secrets_registry import mask_config, merge_secret_update
from app.services.config_io import _sanitize_imported_config
from app.utils.redact import safe_url_display


# ── safe_url_display ─────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://user:pass@host/path", "https://host/…"),           # userinfo dropped
    ("https://hooks.slack.com/services/T/B/XXXX", "https://hooks.slack.com/…"),
    ("https://api.telegram.org/bot123:ABC/sendMessage", "https://api.telegram.org/…"),
    ("https://example.com/hook?token=secret", "https://example.com/…"),
    ("https://example.com", "https://example.com"),              # no path/query
    ("https://example.com/", "https://example.com"),             # bare slash
    ("https://example.com:8443/x", "https://example.com:8443/…"),  # port kept
    ("", ""),
])
def test_safe_url_display(url, expected):
    assert safe_url_display(url) == expected


def test_safe_url_display_passes_non_strings():
    assert safe_url_display(None) is None
    assert safe_url_display(123) == 123


def test_safe_url_display_never_leaks_the_secret():
    for url in (
        "https://user:S3CRET@host/x",
        "https://hooks.slack.com/services/T/B/TOPSECRETTOKEN",
        "https://h/hook?api_key=LEAK",
    ):
        out = safe_url_display(url)
        assert "S3CRET" not in out and "TOPSECRETTOKEN" not in out and "LEAK" not in out


# ── mask_config redacts the url across resources ─────────────────

def test_mask_config_redacts_webhook_url_and_masks_token():
    out = mask_config("channel", "webhook", {
        "url": "https://hooks.slack.com/services/T/B/XXXX", "auth_value": "tok",
    })
    assert out["url"] == "https://hooks.slack.com/…"
    assert out["auth_value"] == "<redacted>"


def test_mask_config_redacts_http_poll_url_userinfo():
    out = mask_config("input", "http_poll", {"url": "https://u:p@host/poll"})
    assert out["url"] == "https://host/…"


def test_mask_config_redacts_sms_gateway_url():
    out = mask_config("channel", "sms", {"gateway_url": "https://gw.test/api?token=x"})
    assert out["gateway_url"] == "https://gw.test/…"


# ── merge: echo of the display must not clobber the stored URL ────

def test_merge_keeps_url_on_redacted_echo():
    old = {"url": "https://h.test/real-secret-path"}
    echoed = {"url": safe_url_display(old["url"])}        # client sends back the display
    merged = merge_secret_update("channel", "webhook", old, echoed)
    assert merged["url"] == "https://h.test/real-secret-path"


def test_merge_replaces_url_with_a_real_new_value():
    old = {"url": "https://h.test/old"}
    merged = merge_secret_update("channel", "webhook", old, {"url": "https://h2.test/new"})
    assert merged["url"] == "https://h2.test/new"


def test_merge_takes_url_when_there_was_none():
    merged = merge_secret_update("channel", "webhook", {}, {"url": "https://h.test/x"})
    assert merged["url"] == "https://h.test/x"


# ── config import: redacted display preserves / drops, real URL kept ──

def test_import_preserves_live_url_on_redacted_echo():
    clean, dropped = _sanitize_imported_config(
        {"url": "https://h/…", "method": "POST"},
        {"url": "https://h/real-secret-path", "method": "GET"},
    )
    assert clean["url"] == "https://h/real-secret-path"


def test_import_drops_redacted_url_with_nothing_to_restore():
    clean, dropped = _sanitize_imported_config({"url": "https://h/…"}, {})
    assert "url" not in clean
    assert "url" in dropped


def test_import_keeps_a_real_imported_url():
    clean, _ = _sanitize_imported_config({"url": "https://h/real"}, {})
    assert clean["url"] == "https://h/real"


# ── API: read redaction, PATCH echo-preserve, masked export ──────

async def test_channel_read_redacts_credential_url(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.post("/v1/channels", json={
        "name": "wh_a06", "kind": "webhook",
        "config": {"url": "https://hooks.slack.com/services/T/B/SECRETTOKEN"},
    }, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["config"]["url"] == "https://hooks.slack.com/…"
    assert "SECRETTOKEN" not in r.text


async def test_patch_echoing_redacted_url_keeps_the_stored_url(db_client, admin_key, db_session):
    h = {"X-API-Key": admin_key}
    real = "https://hooks.slack.com/services/T/B/KEEPME"
    cid = (await db_client.post("/v1/channels", json={
        "name": "wh_a06_patch", "kind": "webhook", "config": {"url": real},
    }, headers=h)).json()["id"]

    # The UI received the redacted display; echo it back while changing method.
    r = await db_client.patch(f"/v1/channels/{cid}", json={
        "config": {"url": "https://hooks.slack.com/…", "method": "PUT"},
    }, headers=h)
    assert r.status_code == 200, r.text

    row = (await db_session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
    assert row.config["url"] == real          # the live URL survived the echo
    assert row.config["method"] == "PUT"      # the real edit still applied


def test_webhook_error_scrubs_the_destination_url():
    from app.channels.webhook import _safe_err

    url = "https://hooks.slack.com/services/T/B/SECRETTOKEN"
    err = _safe_err(url, f"HTTP error: ConnectError: failed to POST {url}")
    assert "SECRETTOKEN" not in err
    assert "hooks.slack.com/…" in err


def test_webhook_error_redacts_userinfo_and_query():
    from app.channels.webhook import _safe_err

    err = _safe_err("https://user:SECRETPW@h/x?token=QTOKEN",
                    "boom at https://user:SECRETPW@h/x?token=QTOKEN")
    assert "SECRETPW" not in err and "QTOKEN" not in err


async def test_masked_export_redacts_the_url(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    await db_client.post("/v1/channels", json={
        "name": "wh_a06_export", "kind": "webhook",
        "config": {"url": "https://hooks.slack.com/services/T/B/EXPORTSECRET"},
    }, headers=h)
    r = await db_client.get("/v1/config/export", params={"mask_secrets": "true"}, headers=h)
    assert r.status_code == 200, r.text
    assert "EXPORTSECRET" not in r.text
    assert "hooks.slack.com/…" in r.text
