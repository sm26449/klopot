"""Redaction helpers for logs and stored error strings (audit R07).

Credential-bearing URLs (Telegram embeds the bot token in the path; httpx
exception messages include the request URL; some webhook URLs carry a token
in userinfo or a query param) must not reach logs, ``failed_channels`` or API
error bodies verbatim.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

# user:pass@host → <redacted>@host
_USERINFO = re.compile(r"(://)[^/@\s]+@")
# Telegram bot path: /bot<token>/... → /bot<redacted>/...
_TG_BOT = re.compile(r"/bot[^/\s]+")
# Secret-ish query parameters.
_QUERY_SECRET = re.compile(
    r"([?&](?:token|api[_-]?key|access_token|auth|key|sig|signature|password|secret)=)"
    r"[^&\s]+",
    re.IGNORECASE,
)

_MASK = "<redacted>"


def redact_url(text: Any) -> Any:
    """Return ``text`` with credential-bearing URL parts masked.

    Safe on any string (bare URL, or an exception message that embeds one);
    non-strings and empty values are returned unchanged.
    """
    if not text or not isinstance(text, str):
        return text
    s = _USERINFO.sub(r"\1" + _MASK + "@", text)
    s = _TG_BOT.sub("/bot" + _MASK, s)
    s = _QUERY_SECRET.sub(r"\1" + _MASK, s)
    return s


# Marker appended when a destination URL's path/query/userinfo is collapsed.
_URL_ELLIPSIS = "/…"


def safe_url_display(url: Any) -> Any:
    """Return a display-safe form of a destination URL (webhook ``url``,
    ``gateway_url``, …).

    Such a URL can carry a credential in userinfo (``user:pass@``), a query
    parameter (``?token=``), or the path itself (Slack ``/services/…``,
    Discord ``/api/webhooks/…``, Telegram ``/bot<token>``). A path segment
    can't be reliably classified as secret-or-not, so we keep only the
    unambiguously safe ``scheme://host[:port]`` and collapse anything beyond
    it to an ellipsis — the operator still sees WHERE a channel points,
    never the secret. Non-strings/empties pass through; an unparseable or
    host-less string falls back to best-effort string redaction.
    """
    if not url or not isinstance(url, str):
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return redact_url(url)
    if not parts.scheme or not parts.hostname:
        return redact_url(url)
    host = parts.hostname
    if parts.port:
        host = f"{host}:{parts.port}"
    base = f"{parts.scheme}://{host}"
    # Userinfo, any real path, or a query string could all carry a secret.
    secret_bearing = bool(parts.username or parts.path.strip("/") or parts.query)
    return f"{base}{_URL_ELLIPSIS}" if secret_bearing else base


def is_redacted_url_display(value: Any) -> bool:
    """True if ``value`` looks like output of :func:`safe_url_display` (so it
    must never be written back over a stored URL on a masked round-trip)."""
    return isinstance(value, str) and (value.endswith(_URL_ELLIPSIS) or _MASK in value)
