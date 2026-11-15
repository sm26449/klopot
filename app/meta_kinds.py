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
    show_if: dict[str, list[Any]] | None = None,
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
    if show_if is not None:
        # Shown (and read by the adapter) only when every named field has one
        # of the listed values — e.g. {"provider": ["twilio"]}.
        field["show_if"] = show_if
    return field


# ── Channel kinds ──────────────────────────────────────────────────
# Fields the channel adapter reads from ``config``. Secret fields are
# flagged post-hoc from the registry so this list stays declarative.

_CHANNELS: dict[str, list[dict[str, Any]]] = {
    "mqtt": [
        _f("topic_template", default="klopot/notifications/{type}", help="Publish topic; placeholders: type, severity, id, instance, channel. No + or #."),
        _f("qos", "int", default=1, help="Delivery QoS: 0, 1 or 2. Consumers deduplicate outbox retries using delivery_id."),
        _f("retain", "bool", default=False, help="Retain notification messages. Off by default to avoid replaying old alerts on subscribe."),
        _f("host", help="Broker host; omit to use ALERTD_MQTT_HOST."),
        _f("port", "int", default=1883, help="Broker TCP port."),
        _f("username", help="Broker username (write-only); defaults to ALERTD_MQTT_USERNAME."),
        _f("password", help="Broker password (write-only); defaults to ALERTD_MQTT_PASSWORD."),
        _f("tls", "bool", default=False, help="TLS with certificate and hostname verification using system CAs."),
        _f("instance_id", help="Availability/heartbeat instance name; defaults to ALERTD_MQTT_CLIENT_ID."),
        _f("availability_topic", default="klopot/{instance}/outputs/{channel}/status", help="Retained online/offline + LWT. Empty disables."),
        _f("heartbeat_topic", default="klopot/{instance}/outputs/{channel}/heartbeat", help="30-second process heartbeat with last successful engine tick. Empty disables."),
        _f("payload_template", "text", help="Optional JSON-object template. delivery_id is always supplied. Use | jsonstr for embedded text."),
        _f("timeout_sec", "int", default=10, help="Connect/publish wait, 1–20 seconds; outbox handles retries."),
    ],
    "ui": [],
    "banner": [],
    "telegram": [
        _f("chat_id", "string", required=True, help="Target chat / channel id."),
        _f("bot_token", "string", help="Bot API token (write-only)."),
        _f("parse_mode", "select", default="HTML", options=["HTML", "MarkdownV2", ""],
           help="Telegram message formatting."),
        _f("inline_actions", "bool", default=False,
           help="Enable acknowledge/snooze buttons and a dedicated bot's long-poll receiver."),
        _f("allowed_user_ids", "json", default=[],
           help="JSON array of Telegram user IDs allowed to act. An allowlist takes precedence over any_chat_member."),
        _f("any_chat_member", "bool", default=False,
           help="Explicitly allow anyone using buttons in this chat when no user allowlist is set."),
        _f("actions_locale", "select", default="en", options=["en", "ro"],
           help="Language of message action buttons."),
        _f("admin_url", "string", default="",
           help="Optional full admin URL for the read-only Open in Klopot link; no credentials, query or fragment."),
    ],
    "sms": [
        _f("provider", "select", default="http", options=["http", "twilio", "teltonika"],
           help="http = any gateway with an HTTP API; twilio = Twilio; teltonika = a Teltonika RUT router (RutOS)."),
        _f("phone", "string", required=True, help="Destination E.164 number; several separated by commas."),
        _f("max_chars", "int", default=320, help="Longer text is cut (160 = one SMS segment)."),
        # provider = http
        _f("url", "string", show_if={"provider": ["http"]},
           help="Gateway send URL. Shown redacted as scheme://host/… on read; leave unchanged to keep it."),
        _f("method", "select", default="POST", options=["POST", "PUT", "GET"], show_if={"provider": ["http"]}),
        _f("content_type", "select", default="application/json",
           options=["application/json", "application/x-www-form-urlencoded", "text/plain"],
           show_if={"provider": ["http"]}),
        _f("body_template", "text", default='{"phone": "{phone | jsonstr}", "message": "{text | jsonstr}"}',
           show_if={"provider": ["http"]},
           help="Request body; {phone} and {text} plus {title} {message} {severity} {type}. "
                "Use | jsonstr inside JSON strings."),
        _f("auth_kind", "select", default="", options=["", "bearer", "basic", "header"],
           show_if={"provider": ["http"]}, help="How auth_value is sent."),
        _f("auth_header", "string", default="Authorization", show_if={"provider": ["http"]},
           help="Header name when auth_kind=header (e.g. X-API-Key)."),
        _f("auth_value", "string", show_if={"provider": ["http"]}, help="Token / key (write-only)."),
        _f("health_url", "string", show_if={"provider": ["http"]},
           help="Optional URL the channel test probes with GET."),
        _f("success_statuses", "json", default=[], show_if={"provider": ["http"]},
           help="Extra HTTP statuses that count as delivered, e.g. [409] when the gateway answers "
                "409 for a duplicate it already sent. 2xx always count; 429/503 wait for "
                "Retry-After; other 4xx fail without retries."),
        # provider = twilio
        _f("account_sid", "string", show_if={"provider": ["twilio"]}),
        _f("auth_token", "string", show_if={"provider": ["twilio"]}, help="Twilio auth token (write-only)."),
        _f("from_number", "string", show_if={"provider": ["twilio"]}, help="Your Twilio number, E.164."),
        # provider = teltonika
        _f("router_url", "string", show_if={"provider": ["teltonika"]},
           help="Router address, e.g. https://192.0.2.1 (RutOS REST API)."),
        _f("username", "string", show_if={"provider": ["teltonika"]}),
        _f("password", "string", show_if={"provider": ["teltonika"]}, help="Router password (write-only)."),
        _f("modem", "string", default="1-1", show_if={"provider": ["teltonika"]}, help="Modem id on the router."),
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
        # Devices are added from the admin UI (Account → Notifications on this
        # device), not in the channel config — the adapter fans out to every
        # enabled device (docs/WEB_PUSH.md). The channel holds the VAPID
        # identity; the public key is derived from the private one.
        _f("vapid_private", "string",
           help="VAPID private key (write-only) — best as a reference to KLOPOT_SECRET_VAPID_PRIVATE "
                "(scripts/vapid_keys.py prints one)."),
        _f("vapid_subject", "string", required=True,
           help="mailto: or https: contact the push services can reach, e.g. mailto:ops@example.com."),
        _f("ttl_sec", "int", default=86400,
           help="How long a push service keeps an alert for a phone that is off (seconds)."),
    ],
    "ntfy": [
        _f("server_url", "string", default="https://ntfy.sh",
           help="ntfy server (self-hosted or https://ntfy.sh)."),
        _f("topic", "string", required=True,
           help="Topic to publish to (write-only: on ntfy, whoever knows the topic can read and post to it)."),
        _f("token", "string", help="Access token (write-only), sent as Bearer."),
        _f("priority_map", "json", default={"info": 2, "warning": 3, "critical": 5},
           help="ntfy priority (1–5) per severity."),
        _f("tags", "json", help='Extra tags, e.g. ["home", "ops"]. The severity is always added.'),
        _f("admin_url", "string",
           help="Public Klopot URL, e.g. https://alerts.example.com — adds a click link and a View button."),
        _f("timeout_sec", "int", default=10),
    ],
    "gotify": [
        _f("server_url", "string", required=True, help="Your Gotify server, e.g. https://gotify.example.com."),
        _f("app_token", "string", help="Application token (write-only), sent as X-Gotify-Key."),
        _f("priority_map", "json", default={"info": 2, "warning": 5, "critical": 8},
           help="Gotify priority (0–10) per severity."),
        _f("admin_url", "string", help="Public Klopot URL — the notification opens the alert in Klopot."),
        _f("timeout_sec", "int", default=10),
    ],
    "pushover": [
        _f("user_key", "string", required=True, help="Your Pushover user (or group) key."),
        _f("app_token", "string", help="Pushover application API token (write-only)."),
        _f("device", "string", help="Only this device (optional)."),
        _f("priority_map", "json", default={"info": -1, "warning": 0, "critical": 1},
           help="Pushover priority (-2…1) per severity. 2 (emergency) is only used via emergency_for."),
        _f("emergency_for", "json", default=[],
           help='Severities sent as EMERGENCY (repeat until acknowledged), e.g. ["critical"]. Off by default.'),
        _f("retry_sec", "int", default=60, help="Emergency: seconds between repeats (≥ 30)."),
        _f("expire_sec", "int", default=3600, help="Emergency: stop repeating after (≤ 10800)."),
        _f("admin_url", "string", help="Public Klopot URL — adds a link to the alert."),
        _f("timeout_sec", "int", default=10),
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
    "alertmanager": [
        _f("default_type", "string", required=True, default="alertmanager_alert",
           help="Template for an alert no other choice matches (unknown alert names are "
                "never dropped). It can use {labels.alertname}, {labels.instance}, "
                "{annotations.summary}…"),
        _f("type_label", "string", default="alertname",
           help="If a template is named like this label's value, that template is used."),
        _f("type_by_severity", "json",
           help='Template by labels.severity when type_label gave none, e.g. '
                '{"critical": "am_critical", "warning": "am_warning", "default": "am_info"}.'),
        _f("resolved_type", "string",
           help="Template sent when an alert resolves (optional)."),
        _f("max_alerts", "int", default=200,
           help="Alerts processed per request; the rest count as truncated."),
        _f("auth_required", "bool", default=True,
           help="Require the token as X-Input-Token or Authorization: Bearer."),
        _f("auth_token", "string",
           help="Expected token (write-only). In Alertmanager: http_config.authorization.credentials."),
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
        _f("json_path", "string", help="Dot-path within a JSON payload (e.g. sensor.temperature)."),
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


# Channel kinds that can wake someone up or cost money per message (roadmap
# §5): the admin UI warns when an `info` template is routed to one.
INTRUSIVE_CHANNEL_KINDS = frozenset({"sms", "pushover"})


def describe_kinds() -> dict[str, Any]:
    """Full form-schema document served by ``GET /v1/meta/kinds``."""
    return {
        "channels": {
            kind: {
                "fields": _apply_secret_flags("channel", kind, fields),
                "intrusive": kind in INTRUSIVE_CHANNEL_KINDS,
            }
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


__all__ = ["INTRUSIVE_CHANNEL_KINDS", "describe_kinds"]
