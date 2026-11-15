"""F29: CRUD must reject malformed runtime config and keep CREATE's limits
on PATCH, instead of accepting values that crash at fire time or at the DB."""
from __future__ import annotations

from datetime import time

import pytest
from pydantic import ValidationError

from app.core.gating import _in_quiet_window
from app.schemas.template import TemplateCreate, TemplateUpdate

pytestmark = pytest.mark.anyio


def test_quiet_hours_nonstring_value_rejected_on_create():
    with pytest.raises(ValidationError):
        TemplateCreate(
            type="t", severity="warning", title_template="x",
            quiet_hours={"screen": 123},
        )


def test_quiet_hours_string_value_accepted():
    t = TemplateCreate(
        type="t", severity="warning", title_template="x",
        quiet_hours={"ui": "22-07"},
    )
    assert t.quiet_hours == {"ui": "22-07"}


def test_quiet_hours_nonstring_rejected_on_update():
    with pytest.raises(ValidationError):
        TemplateUpdate(quiet_hours={"ui": 5})


def test_update_locale_respects_create_max_length():
    with pytest.raises(ValidationError):
        TemplateUpdate(locale="123456789")  # 9 > max 8


def test_in_quiet_window_fails_open_on_nonstring():
    # Defensive: a stale non-string window must not raise AttributeError.
    assert _in_quiet_window(time(23, 0), 123) is False


async def test_create_input_unsupported_kind_is_422(db_client, admin_key):
    r = await db_client.post(
        "/v1/inputs",
        json={"name": "sch", "kind": "schedule", "config": {}},
        headers={"X-API-Key": admin_key},
    )
    assert r.status_code == 422, r.text
    assert "not supported" in r.text


async def test_create_input_supported_kind_ok(db_client, admin_key):
    r = await db_client.post(
        "/v1/inputs",
        json={"name": "wh1", "kind": "webhook", "config": {"auth_token": "a-long-enough-token"}},
        headers={"X-API-Key": admin_key},
    )
    assert r.status_code == 201, r.text


async def test_import_refuses_an_input_kind_without_an_adapter(db_client, admin_key):
    """Copilot hygiene #5: the REST API refused these kinds, an import stored
    them as enabled inputs that never ran."""
    pack = "inputs:\n  - name: mailbox\n    kind: email_imap\n    config: {host: imap.example.com}\n"
    r = await db_client.post("/v1/config/import", params={"apply": "true"}, content=pack,
                             headers={"X-API-Key": admin_key, "Content-Type": "application/yaml"})
    body = r.json()
    assert body.get("ok") is False or r.status_code >= 400, body
    assert "not supported" in r.text
    names = [i["name"] for i in (await db_client.get("/v1/inputs", headers={"X-API-Key": admin_key})).json()["items"]]
    assert "mailbox" not in names


def test_the_form_offers_only_input_kinds_that_run():
    from app.inputs import REGISTRY
    from app.meta_kinds import describe_kinds

    offered = set(describe_kinds()["inputs"])
    assert offered == set(REGISTRY)
    assert "email_imap" not in offered and "schedule" not in offered
