"""Inbound inputs: make the old authentication behaviour explicit.

Until 1.2 an inbound input (webhook, sms_inbox, alertmanager) without an
``auth_required`` flag demanded a token only if one was configured — without
one it accepted posts from anyone. Now a token is always required unless the
config says ``auth_required: false`` (app/inputs/webhook.py). So that no
existing input changes behaviour on upgrade:

- no flag and no token → ``auth_required: false`` (it was open; it stays
  open, but now visibly so — the admin UI marks it);
- a flag that is not a boolean → the boolean the old code read from it
  (``bool(value)``: the string "false" meant *required*).

Inputs with a token and no flag need nothing: required then, required now.

Revision ID: 0041
Revises: 0040
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_INBOUND = ("webhook", "sms_inbox", "alertmanager")


def _explicit(config: dict) -> dict | None:
    """The config with its old behaviour spelled out, or None if unchanged."""
    if "auth_required" in config:
        flag = config["auth_required"]
        return None if isinstance(flag, bool) else {**config, "auth_required": bool(flag)}
    if config.get("auth_token") or config.get("auth_token_ref"):
        return None
    return {**config, "auth_required": False}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config FROM inputs WHERE kind IN :kinds").bindparams(
            sa.bindparam("kinds", expanding=True)),
        {"kinds": list(_INBOUND)},
    ).all()
    for row_id, raw in rows:
        config = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        new = _explicit(config)
        if new is not None:
            bind.execute(sa.text("UPDATE inputs SET config = :c WHERE id = :i"),
                         {"c": json.dumps(new), "i": row_id})


def downgrade() -> None:
    # Data only, and the explicit form means the same under the old code.
    pass
