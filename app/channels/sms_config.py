"""SMS channel config: provider checks and the pre-0031 config shape.

Before migration 0031 the SMS channel spoke one gateway API only:
``{"gateway_url", "phone", "gateway_api_key"|"gateway_api_key_ref"}`` and it
POSTed ``{"phone", "message"}`` to ``<gateway_url>/api/sms/send`` with the key
in ``X-API-Key``. :func:`upgrade_legacy` rewrites that shape into the generic
``http`` provider producing exactly the same request, so such a gateway keeps
working and old exports / API clients still import. Migration 0031 applies
the same rewrite to stored channels.
"""
from __future__ import annotations

from typing import Any

PROVIDERS = ("http", "twilio", "teltonika")
LEGACY_BODY = '{"phone": "{phone | jsonstr}", "message": "{text | jsonstr}"}'

# Non-secret fields each provider needs, and the secrets (literal or *_ref).
_REQUIRED: dict[str, tuple[str, ...]] = {
    "http": ("url",),
    "twilio": ("account_sid", "from_number"),
    "teltonika": ("router_url", "username"),
}
_REQUIRED_SECRETS: dict[str, tuple[str, ...]] = {
    "twilio": ("auth_token",),
    "teltonika": ("password",),
}


def is_legacy(config: dict[str, Any]) -> bool:
    return bool(config.get("gateway_url")) and not config.get("provider") and not config.get("url")


def upgrade_legacy(config: dict[str, Any]) -> dict[str, Any]:
    """The generic ``http`` form of a pre-0031 SMS config (unchanged otherwise)."""
    if not is_legacy(config):
        return config
    out = {k: v for k, v in config.items() if not k.startswith("gateway_")}
    base = str(config["gateway_url"]).rstrip("/")
    out.update({
        "provider": "http",
        "url": f"{base}/api/sms/send",
        "method": "POST",
        "content_type": "application/json",
        "body_template": LEGACY_BODY,
        "health_url": f"{base}/api/health",
    })
    if config.get("gateway_api_key_ref") or config.get("gateway_api_key"):
        out.update({"auth_kind": "header", "auth_header": "X-API-Key"})
        if config.get("gateway_api_key_ref"):
            out["auth_value_ref"] = config["gateway_api_key_ref"]
        if config.get("gateway_api_key"):
            out["auth_value"] = config["gateway_api_key"]
    return out


def success_statuses(config: dict[str, Any]) -> frozenset[int]:
    """Extra HTTP statuses the http provider counts as delivered (e.g. 409 =
    "duplicate, an earlier request already covers it"); 2xx always are."""
    raw = config.get("success_statuses") or []
    return frozenset(int(x) for x in raw if isinstance(x, int) and not isinstance(x, bool))


def validate_config(config: dict[str, Any], *, require_secrets: bool = True) -> None:
    """Raise ValueError naming what the chosen provider is missing."""
    provider = config.get("provider") or "http"
    if provider not in PROVIDERS:
        raise ValueError(f"SMS provider must be one of: {', '.join(PROVIDERS)}")
    missing = [f for f in ("phone", *_REQUIRED[provider]) if not str(config.get(f) or "").strip()]
    if require_secrets:
        missing += [s for s in _REQUIRED_SECRETS.get(provider, ())
                    if not (config.get(s) or config.get(f"{s}_ref"))]
    if missing:
        raise ValueError(f"SMS provider '{provider}' needs: {', '.join(missing)}")
    statuses = config.get("success_statuses")
    if statuses not in (None, []) and (not isinstance(statuses, list) or not all(
            isinstance(x, int) and not isinstance(x, bool) and 100 <= x <= 599 for x in statuses)):
        raise ValueError("SMS success_statuses must be a list of HTTP status codes, e.g. [409]")
    if config.get("auth_kind") not in (None, "", "bearer", "basic", "header"):
        raise ValueError("SMS auth_kind must be bearer, basic or header")
