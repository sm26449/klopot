"""Registry of secret-bearing config fields, per resource kind.

Single source of truth for three concerns that must agree:

1. **Masking on read** — ``GET /v1/channels`` / ``GET /v1/inputs`` and
   the ``audit_log`` before/after snapshots must never carry a literal
   secret (``mask_config``).
2. **Merge on write** — ``PATCH`` replaces ``config`` wholesale, so a
   client that received a masked config and sends it back must not
   wipe the stored secret. A secret field that is *omitted* or ``null``
   keeps its current value; an empty string clears it; any other
   string replaces it (``merge_secret_update``).
3. **UI form generation** (F3, ``/v1/meta/kinds``) — which fields are
   rendered as write-only secret inputs.

Convention (``docs/SCHEMA.md``): a secret field ``foo`` may be stored
either as the literal ``foo`` (development convenience) or as a
reference ``foo_ref`` holding an environment-variable NAME. The
``_ref`` sibling is *not* a secret — it is the name of one — and is
always returned as-is.

Kinds not listed fall back to a name heuristic so a future adapter
that forgets to register still gets masked.
"""
from __future__ import annotations

from typing import Any

from .utils.redact import safe_url_display

_REF_SUFFIX = "_ref"

# resource → kind → literal secret field names
SECRET_FIELDS: dict[str, dict[str, frozenset[str]]] = {
    "channel": {
        "mqtt": frozenset({"username", "password"}),
        "telegram": frozenset({"bot_token"}),
        # gateway_api_key: pre-0031 shape, still masked if an old config arrives.
        "sms": frozenset({"auth_value", "auth_token", "password", "gateway_api_key", "api_key"}),
        "email": frozenset({"password"}),
        "webhook": frozenset({"auth_value"}),
        # The topic name is the credential on ntfy: whoever knows it can
        # subscribe and publish (review K09).
        "ntfy": frozenset({"token", "topic"}),
        "gotify": frozenset({"app_token"}),
        "pushover": frozenset({"app_token", "user_key"}),
        "push": frozenset({"vapid_private"}),
        "ui": frozenset(),
        "banner": frozenset(),
    },
    "input": {
        "mqtt": frozenset({"password", "username"}),
        "webhook": frozenset({"auth_token"}),
        "sms_inbox": frozenset({"auth_token"}),  # subclass of webhook
        "alertmanager": frozenset({"auth_token"}),  # subclass of webhook
        "http_poll": frozenset({"auth_value"}),
        "schedule": frozenset(),
        "email_imap": frozenset({"password"}),
    },
}

# Name heuristic for unregistered kinds / unknown keys. Deliberately
# narrower than config_io._SECRET_HINTS ("key" alone would match
# nothing harmful today but is too broad to trust).
_HEURISTIC_MARKERS = ("password", "token", "secret", "api_key", "auth_value", "private")
_HEURISTIC_EXCLUDE = frozenset({"auth_required", "auth_kind", "parse_mode"})

MASK = "<redacted>"


def _kind_str(kind: Any) -> str:
    return getattr(kind, "value", kind) or ""


def _is_heuristic_secret(key: str) -> bool:
    k = key.lower()
    if k.endswith(_REF_SUFFIX) or k in _HEURISTIC_EXCLUDE:
        return False
    return any(m in k for m in _HEURISTIC_MARKERS)


def is_url_display_key(key: str) -> bool:
    """True for a destination-URL field whose value is shown redacted rather
    than masked wholesale (webhook ``url``, sms ``gateway_url``, …) — audit
    A-06. The value can carry a credential, but the host is useful to show."""
    k = str(key).lower()
    if k.endswith(_REF_SUFFIX):
        return False
    return k == "url" or k.endswith("_url")


def secret_fields(resource: str, kind: Any) -> frozenset[str]:
    """Registered literal secret fields for ``(resource, kind)``.

    Unknown kinds return an empty set; callers combine with
    :func:`is_secret_key` to still catch heuristically-named keys.
    """
    return SECRET_FIELDS.get(resource, {}).get(_kind_str(kind), frozenset())


def is_secret_key(resource: str, kind: Any, key: str) -> bool:
    """True if ``key`` holds a literal secret for this resource/kind."""
    return key in secret_fields(resource, kind) or _is_heuristic_secret(key)


# Sensitive keys that can appear NESTED (webhook ``headers`` map, etc.)
# — not top-level channel/input secret fields, so the registry + heuristic
# alone miss them (audit A08: ``headers.Authorization`` leaked verbatim).
_SENSITIVE_NESTED = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "apikey", "x-auth-token", "x-token", "x-auth",
})


def _is_sensitive_nested_key(key: str) -> bool:
    k = str(key).lower()
    if k.endswith(_REF_SUFFIX) or k in _HEURISTIC_EXCLUDE:
        return False
    return k in _SENSITIVE_NESTED or any(m in k for m in _HEURISTIC_MARKERS)


def _mask_nested(value: Any) -> Any:
    """Recursively mask secret-looking keys inside dicts/lists."""
    if isinstance(value, dict):
        return {
            k: (MASK if (_is_sensitive_nested_key(k) and v not in (None, ""))
                else _mask_nested(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_nested(x) for x in value]
    return value


def mask_config(resource: str, kind: Any, cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of ``cfg`` with literal secrets replaced by ``MASK``.

    Masks registered/heuristic secret fields at the top level AND secret-
    looking keys nested in dicts/lists (webhook ``headers``, etc. — audit
    A08). ``*_ref`` names are preserved — they identify *where* the secret
    lives, not the secret itself. A destination-URL field (``url``,
    ``gateway_url``) is shown as a safe ``scheme://host/…`` display rather
    than its raw value, since the userinfo / query / path can carry a
    credential (audit A-06).
    """
    out: dict[str, Any] = {}
    for k, v in (cfg or {}).items():
        if is_secret_key(resource, kind, k) and v not in (None, ""):
            out[k] = MASK
        elif is_url_display_key(k) and isinstance(v, str) and v:
            out[k] = safe_url_display(v)
        elif isinstance(v, dict | list):
            out[k] = _mask_nested(v)
        else:
            out[k] = v
    return out


def secret_status(resource: str, kind: Any, cfg: dict[str, Any] | None) -> dict[str, str]:
    """Describe how each secret field is provided, without exposing it.

    Returns ``{field: "literal" | "env:<NAME>" | "secret:<NAME>"}`` for
    every registered secret field that is set either literally or via
    its ``_ref`` sibling. Unset fields are omitted. Used by
    ``ChannelRead.secret_fields_set`` / ``InputRead.secret_fields_set``
    so the UI can show "configured" without seeing the value.
    """
    cfg = cfg or {}
    status: dict[str, str] = {}
    fields = set(secret_fields(resource, kind)) | {
        k for k in cfg if _is_heuristic_secret(k)
    }
    for f in sorted(fields):
        ref = cfg.get(f + _REF_SUFFIX)
        if ref:
            ref_s = str(ref)
            status[f] = ref_s if ":" in ref_s else f"env:{ref_s}"
        elif cfg.get(f) not in (None, ""):
            status[f] = "literal"
    return status


_MISSING = object()


def _merge_secret_leaf(old_v: Any, new_v: Any) -> tuple[bool, Any]:
    """Write rule for one secret leaf. Returns ``(keep, value)``:

      - omitted / ``None`` / ``MASK`` → keep the old value (or drop the key
        if there was none) — a client that received a masked read and
        echoes it back must not wipe the stored secret.
      - ``""`` → clear (drop the key).
      - anything else → replace with the new value.
    """
    if new_v is _MISSING or new_v is None or new_v == MASK:
        return (old_v is not _MISSING, old_v)
    if new_v == "":
        return (False, None)
    return (True, new_v)


def _merge_nested(old: Any, new: Any) -> Any:
    """Recursively merge ``new`` onto ``old`` applying the secret-leaf rule
    to ``_is_sensitive_nested_key`` fields (webhook ``headers`` etc.) and
    recursing into nested dicts/lists (audit F17). Non-secret scalars are
    taken from ``new`` (wholesale replace); secret keys present in ``old``
    but omitted in ``new`` are preserved.
    """
    if isinstance(new, list):
        old_list = old if isinstance(old, list) else []
        out_list: list[Any] = []
        for i, item in enumerate(new):
            old_item = old_list[i] if i < len(old_list) else _MISSING
            if isinstance(item, dict | list):
                base = old_item if isinstance(old_item, dict | list) else (
                    {} if isinstance(item, dict) else []
                )
                out_list.append(_merge_nested(base, item))
            else:
                out_list.append(item)
        return out_list
    if not isinstance(new, dict):
        return new

    old_d = old if isinstance(old, dict) else {}
    out: dict[str, Any] = {}
    secret_keys = {
        k for k in set(old_d) | set(new) if _is_sensitive_nested_key(k)
    }
    for k in secret_keys:
        keep, val = _merge_secret_leaf(old_d.get(k, _MISSING), new.get(k, _MISSING))
        if keep:
            out[k] = val
    for k, v in new.items():
        if k in secret_keys:
            continue
        if isinstance(v, dict | list):
            out[k] = _merge_nested(old_d.get(k), v)
        else:
            out[k] = v
    return out


def merge_secret_update(
    resource: str, kind: Any, old_cfg: dict[str, Any] | None, new_cfg: dict[str, Any] | None
) -> dict[str, Any]:
    """Apply write semantics for secret fields on a full-config PATCH.

    Top-level literal secret fields of this kind, and secret-looking keys
    nested in dicts/lists (webhook ``headers``, HTTP-poll headers, nested
    maps/lists — audit F17), follow the same rule:

      - omitted or ``None`` → keep the old value
      - ``""`` → clear (field removed)
      - ``MASK`` (client echoed a masked read back) → keep old value
      - any other value → replace

    Other (non-secret) keys come from ``new_cfg``; container values are
    merged recursively so a masked nested secret inside them survives.
    """
    old = old_cfg or {}
    new = new_cfg or {}
    out: dict[str, Any] = {}
    top_secrets = set(secret_fields(resource, kind)) | {
        k for k in set(old) | set(new) if _is_heuristic_secret(k)
    }
    for f in top_secrets:
        keep, val = _merge_secret_leaf(old.get(f, _MISSING), new.get(f, _MISSING))
        if keep:
            out[f] = val
    for k, v in new.items():
        if k in top_secrets:
            continue
        if is_url_display_key(k) and isinstance(v, str):
            # A client that received the redacted display and echoes it back
            # must not overwrite the stored URL with the display (audit A-06).
            old_v = old.get(k)
            out[k] = old_v if (isinstance(old_v, str) and v == safe_url_display(old_v)) else v
        elif isinstance(v, dict | list):
            out[k] = _merge_nested(old.get(k), v)
        else:
            out[k] = v
    return out


__all__ = [
    "MASK",
    "SECRET_FIELDS",
    "is_secret_key",
    "is_url_display_key",
    "mask_config",
    "merge_secret_update",
    "secret_fields",
    "secret_status",
]
