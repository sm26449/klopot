"""Declarative field schemas per resource kind — the single source of
truth for the admin UI's channel / input / variable forms (F3.10).

Why a hand-written dict and not adapter introspection: the adapters
read loosely-typed ``config`` dicts (``config.get("host")``), so there
is no typed schema to reflect on. Rather than scatter field lists
across the UI JS, every form is generated from ``describe_kinds()``
here. Adding a field to a form is a one-line change in this file that
both the UI and ``docs/EXTENSIBILITY.md`` point at.

Secret-ness is NOT duplicated: a field is marked ``secret`` iff it is a
registered secret for that kind in :mod:`app.secrets_registry`, so the
two can never drift. A secret field implies a ``<name>_ref`` sibling
(env-var reference) the UI offers alongside the write-only value box.

Shape returned by :func:`describe_kinds`::

    {
      "channels": {
        "telegram": {"fields": [Field, ...]},
        ...
      },
      "inputs": {...},
      "variables": {...},        # keyed by VariableSource
      "webhook_presets": [Preset, ...],
    }

``Field`` = {name, type, required, secret, default, help, options?, ref_field?}
``type`` ∈ {string, text, int, float, bool, json, select, topic, cron}
"""
from __future__ import annotations

from typing import Any

from .secrets_registry import secret_fields

# ── Field helpers ──────────────────────────────────────────────────


def _f(
    name: str,
    type: str = "string",
    *,
    required: bool = False,
    default: Any = None,
    help: str = "",
    options: list[str] | None = None,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "name": name,
        "type": type,
        "required": required,
        "secret": False,
        "default": default,
        "help": help,
    }
    if options is not None:
        field["options"] = options
    return field


# ── Channel kinds ──────────────────────────────────────────────────
# Fields the channel adapter reads from ``config``. Secret fields are
# flagged post-hoc from the registry so this list stays declarative.

_CHANNELS: dict[str, list[dict[str, Any]]] = {
    "ui": [],
    "banner": [],
    "telegram": [
        _f("chat_id", "string", required=True, help="Target chat / channel id."),
        _f("bot_token", "string", help="Bot API token (write-only)."),
        _f("parse_mode", "select", default="HTML", options=["HTML", "MarkdownV2", ""],
           help="Telegram message formatting."),
    ],
    "sms": [
        _f("phone", "string", required=True, help="Destination E.164 number."),
        _f("gateway_url", "string", required=True,
           help="SMS gateway base URL (http://sms-gateway:5080). Shown redacted "
                "as scheme://host/… on read; leave unchanged to keep it."),
        _f("gateway_api_key", "string", help="Gateway API key (write-only)."),
    ],
    "email": [
        _f("to", "string", required=True, help="Recipient address(es), comma-separated."),
        _f("smtp_host", "string", required=True),
        _f("smtp_port", "int", default=587),
        _f("username", "string"),
        _f("password", "string", help="SMTP password (write-only)."),
        _f("from_addr", "string",
           help="Envelope sender (canonical). Defaults to username if blank."),
        _f("use_tls", "bool", default=True),
    ],
    "push": [
        # Subscriptions are provisioned externally (per browser), not in the
        # channel config — the adapter fans out to all stored subscriptions
        # (audit F34). The channel only holds the VAPID identity.
        _f("vapid_public", "string"),
        _f("vapid_private", "string", help="VAPID private key (write-only)."),
        _f("vapid_subject", "string",
           help="mailto: or https: contact for VAPID (required to send)."),
    ],
    "webhook": [
        _f("url", "string", required=True,
           help="Target URL. Shown redacted as scheme://host/… on read since the "
                "path/query can carry a secret; leave it unchanged to keep the "
                "stored value, or type a new URL to replace it."),
        _f("method", "select", default="POST", options=["POST", "PUT", "GET"]),
        _f("content_type", "select", default="application/json",
           options=["application/json", "application/x-www-form-urlencoded", "text/plain"]),
        _f("body_template", "text",
           help="Payload template; {title} {message} {severity} {type} placeholders. "
                "For JSON, wrap embedded text with the | jsonstr filter "
                "(e.g. {\"text\": \"{title | jsonstr}\"}). Leave blank for a "
                "default JSON body."),
        _f("auth_kind", "select", default="", options=["", "bearer", "basic", "header"],
           help="How auth_value is applied."),
        _f("auth_header", "string", default="Authorization",
           help="Header name when auth_kind=header."),
        _f("auth_value", "string", help="Token / credential (write-only)."),
        _f("expected_status", "int", default=200,
           help="HTTP status treated as success."),
        _f("timeout_sec", "int", default=10),
    ],
}

# ── Input kinds ────────────────────────────────────────────────────

_INPUTS: dict[str, list[dict[str, Any]]] = {
    "mqtt": [
        _f("host", "string", required=True, help="Broker host."),
        _f("port", "int", default=1883),
        _f("username", "string", help="Broker username (write-only)."),
        _f("password", "string", help="Broker password (write-only)."),
        _f("client_id", "string", help="MQTT client id; defaults to alertd-<input>."),
        _f("keepalive", "int", default=60),
    ],
    "http_poll": [
        _f("url", "string", required=True,
           help="Poll URL. Shown redacted as scheme://host/… on read; leave "
                "unchanged to keep the stored value."),
        _f("method", "select", default="GET", options=["GET", "POST"]),
        _f("params", "json", help="Query params as a JSON object."),
        _f("headers", "json", help="Extra request headers as a JSON object."),
        _f("interval_sec", "int", default=60),
        _f("timeout_sec", "int", default=10),
        _f("auth_kind", "select", default="", options=["", "bearer", "basic", "header"]),
        _f("auth_value", "string", help="Token / credential (write-only)."),
    ],
    "webhook": [
        _f("auth_required", "bool", default=True,
           help="Require X-Input-Token on POST /v1/inputs/{id}/webhook."),
        _f("auth_token", "string", help="Expected inbound token (write-only)."),
    ],
    "sms_inbox": [
        # The adapter does NOT poll — it receives inbound SMS forwarded as
        # HTTP POST to /v1/inputs/{id}/webhook (same path as the webhook
        # input). auth_required defaults True so a configured token is
        # actually enforced; set it False to accept unauthenticated posts
        # (audit F35).
        _f("auth_required", "bool", default=True,
           help="Require X-Input-Token on the inbound POST "
                "/v1/inputs/{id}/webhook. Set False to opt out explicitly."),
        _f("auth_token", "string",
           help="Expected inbound token (write-only), checked when "
                "auth_required is true."),
    ],
    "schedule": [],
    "email_imap": [
        _f("host", "string", required=True),
        _f("port", "int", default=993),
        _f("username", "string", required=True),
        _f("password", "string", help="IMAP password (write-only)."),
        _f("mailbox", "string", default="INBOX"),
        _f("poll_interval_sec", "int", default=60),
    ],
}

# ── Variable sources ───────────────────────────────────────────────
# Fields mirror ``core/variable_resolver.VarMapping`` (config keys).

_VALUE_TYPES = ["number", "bool", "string", "json"]

_VARIABLES: dict[str, list[dict[str, Any]]] = {
    "mqtt": [
        _f("input_id", "int", help="Owning MQTT input id."),
        _f("topic", "topic", required=True, help="MQTT topic (supports + / # wildcards)."),
        _f("json_path", "string", help="Dot-path within a JSON payload (e.g. battery.soc)."),
        _f("type", "select", default="number", options=_VALUE_TYPES,
           help="Coercion applied to the extracted value."),
        _f("stale_after_sec", "int", default=300,
           help="Value is considered stale past this age; rules gate on it."),
    ],
    "aggregate": [
        _f("topics", "json", required=True, help="Member topics as a JSON array."),
        _f("aggregate", "select", default="sum", options=["sum", "avg", "max", "min"]),
        _f("json_path", "string", help="Dot-path within each member payload."),
        _f("type", "select", default="number", options=_VALUE_TYPES),
        _f("stale_after_sec", "int", default=300),
    ],
    "constant": [
        _f("value", "json", required=True, help="Static value (never goes stale)."),
        _f("type", "select", default="number", options=_VALUE_TYPES),
    ],
    "computed": [
        _f("formula", "text", required=True,
           help="Expression over other variables (expression language)."),
        _f("type", "select", default="number", options=_VALUE_TYPES),
        _f("stale_after_sec", "int", default=300),
    ],
    "schedule": [
        _f("cron", "cron", required=True, help="Cron expression for the slot value."),
        _f("value", "json", help="Value to set while the slot is active."),
    ],
}

# ── Webhook presets ────────────────────────────────────────────────
# Prefill a webhook channel for a known target. ``config`` keys here
# are merged into the channel config when the operator picks a preset.

_WEBHOOK_PRESETS: list[dict[str, Any]] = [
    {
        "id": "discord",
        "label": "Discord",
        "config": {
            "content_type": "application/json",
            "expected_status": 204,
            "body_template": '{"content": "**{title | jsonstr}**\\n{message | jsonstr}"}',
        },
        "help": "Channel webhook URL (…/api/webhooks/<id>/<token>).",
    },
    {
        "id": "slack",
        "label": "Slack",
        "config": {
            "content_type": "application/json",
            "expected_status": 200,
            "body_template": '{"text": "*{title | jsonstr}*\\n{message | jsonstr}"}',
        },
        "help": "Incoming webhook URL (hooks.slack.com/services/…).",
    },
    {
        "id": "teams",
        "label": "Microsoft Teams",
        "config": {
            "content_type": "application/json",
            "expected_status": 200,
            "body_template": '{"title": "{title | jsonstr}", "text": "{message | jsonstr}"}',
        },
        "help": "Teams incoming webhook / workflow URL.",
    },
    {
        "id": "mattermost",
        "label": "Mattermost",
        "config": {
            "content_type": "application/json",
            "expected_status": 200,
            "body_template": '{"text": "**{title | jsonstr}**\\n{message | jsonstr}"}',
        },
        "help": "Incoming webhook URL (…/hooks/<token>).",
    },
    {
        "id": "home_assistant",
        "label": "Home Assistant",
        "config": {
            "content_type": "application/json",
            "expected_status": 200,
            "body_template": '{"title": "{title | jsonstr}", "message": "{message | jsonstr}"}',
            "auth_kind": "bearer",
        },
        "help": "Webhook (/api/webhook/<id>) or REST (/api/services/notify/*) with a long-lived token in auth_value.",
    },
    {
        "id": "ntfy",
        "label": "ntfy",
        "config": {
            "content_type": "text/plain",
            "expected_status": 200,
            "body_template": "{message}",
        },
        "help": "Topic URL (https://ntfy.sh/<topic>). Title goes in the body.",
    },
    {
        "id": "generic",
        "label": "Generic JSON",
        "config": {
            "content_type": "application/json",
            "expected_status": 200,
            "body_template": '{"title": "{title | jsonstr}", "message": "{message | jsonstr}", "severity": "{severity}", "type": "{type}"}',
        },
        "help": "Plain JSON POST with the standard fields.",
    },
]


# ── Public builder ─────────────────────────────────────────────────


def _apply_secret_flags(resource: str, kind: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of ``fields`` with ``secret``/``ref_field`` set
    from the secrets registry so the two never drift."""
    secrets = secret_fields(resource, kind)
    out: list[dict[str, Any]] = []
    for f in fields:
        g = dict(f)
        if g["name"] in secrets:
            g["secret"] = True
            g["ref_field"] = g["name"] + "_ref"
        out.append(g)
    return out


def describe_kinds() -> dict[str, Any]:
    """Full form-schema document served by ``GET /v1/meta/kinds``."""
    return {
        "channels": {
            kind: {"fields": _apply_secret_flags("channel", kind, fields)}
            for kind, fields in _CHANNELS.items()
        },
        "inputs": {
            kind: {"fields": _apply_secret_flags("input", kind, fields)}
            for kind, fields in _INPUTS.items()
        },
        "variables": {
            source: {"fields": list(fields)}
            for source, fields in _VARIABLES.items()
        },
        "webhook_presets": [dict(p) for p in _WEBHOOK_PRESETS],
    }


__all__ = ["describe_kinds"]
