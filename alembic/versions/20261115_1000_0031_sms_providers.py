"""SMS channel providers: convert pre-0031 SMS configs to provider ``http``.

The SMS channel used to speak one gateway API only (``gateway_url`` +
``gateway_api_key``: POST ``{"phone","message"}`` to ``/api/sms/send`` with
``X-API-Key``). It now has providers (``http``, ``twilio``, ``teltonika``).
Each stored SMS channel in the old shape is rewritten to the generic ``http``
provider that sends exactly the same request, so it keeps working unchanged.
The rewrite mirrors ``app.channels.sms_config.upgrade_legacy`` (copied, so
this migration never changes when the app code does).

Revision ID: 0031
Revises: 0030
"""
from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

_BODY = '{"phone": "{phone | jsonstr}", "message": "{text | jsonstr}"}'


def _upgrade_config(config: dict[str, Any]) -> dict[str, Any] | None:
    if not config.get("gateway_url") or config.get("provider") or config.get("url"):
        return None
    out = {k: v for k, v in config.items() if not k.startswith("gateway_")}
    base = str(config["gateway_url"]).rstrip("/")
    out.update({"provider": "http", "url": f"{base}/api/sms/send", "method": "POST",
                "content_type": "application/json", "body_template": _BODY,
                "health_url": f"{base}/api/health"})
    if config.get("gateway_api_key_ref") or config.get("gateway_api_key"):
        out.update({"auth_kind": "header", "auth_header": "X-API-Key"})
        if config.get("gateway_api_key_ref"):
            out["auth_value_ref"] = config["gateway_api_key_ref"]
        if config.get("gateway_api_key"):
            out["auth_value"] = config["gateway_api_key"]
    return out


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, config FROM channels WHERE kind = 'sms'")).fetchall()
    for row_id, raw in rows:
        config = json.loads(raw) if isinstance(raw, str | bytes) else (raw or {})
        new = _upgrade_config(config)
        if new is not None:
            conn.execute(sa.text("UPDATE channels SET config = :c WHERE id = :i"),
                         {"c": json.dumps(new), "i": row_id})


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, config FROM channels WHERE kind = 'sms'")).fetchall()
    for row_id, raw in rows:
        config = json.loads(raw) if isinstance(raw, str | bytes) else (raw or {})
        url = str(config.get("url") or "")
        if config.get("provider") != "http" or not url.endswith("/api/sms/send"):
            continue
        old = {k: v for k, v in config.items() if k not in {
            "provider", "url", "method", "content_type", "body_template", "health_url",
            "auth_kind", "auth_header", "auth_value", "auth_value_ref"}}
        old["gateway_url"] = url[: -len("/api/sms/send")]
        if config.get("auth_value_ref"):
            old["gateway_api_key_ref"] = config["auth_value_ref"]
        if config.get("auth_value"):
            old["gateway_api_key"] = config["auth_value"]
        conn.execute(sa.text("UPDATE channels SET config = :c WHERE id = :i"),
                     {"c": json.dumps(old), "i": row_id})
