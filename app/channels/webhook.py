"""Webhook channel — generic HTTP POST with templated body.

This is the swiss-army adapter: Slack, Discord, Mattermost, MS Teams,
Home Assistant, custom internal webhooks. Anything that accepts a
JSON or form POST.

Config shape::

    {
      "url": "https://hooks.slack.com/services/...",
      "method": "POST",                           // POST/PUT
      "content_type": "application/json",         // or "application/x-www-form-urlencoded"
      "headers": {"X-Custom": "value"},           // extra headers
      "body_template": "{\\"text\\": \\"{title | jsonstr}: {message | jsonstr}\\"}",
      "auth_kind": "bearer" | "basic" | "header" | null,
      "auth_value_ref": "SLACK_BEARER_TOKEN",     // env var name
      "expected_status": 200                      // optional explicit success code
    }

Body template uses ``{var}`` substitution (same as message rendering).
For a JSON body, wrap any free-text value embedded in a string literal
with the ``| jsonstr`` filter so quotes/newlines stay valid JSON
(``{"text": "{title | jsonstr}"}``). With no ``body_template`` the
channel emits a default JSON object built via ``json.dumps`` (always
valid). Available vars exposed by the dispatcher:

  ``title``, ``message``, ``severity``, ``icon``, ``type``, ``id``,
  ``rule_id``, ``fired_at``, ``severity_emoji``

Plus everything in ``vars_payload`` if it's a flat dict (so a rule
that fires a ``consumption_high`` alert exposes ``load_kw``,
``ratio_pct``, etc.).
"""
from __future__ import annotations

import json
import logging
from typing import Any, cast

from ..core import rendering
from ..utils.http_retry import BACKPRESSURE_STATUSES, retry_after_or_default
from ..utils.redact import redact_url, safe_url_display
from . import _http
from ._secrets import resolve_secret
from .base import BaseChannel, Notification, SendResult

logger = logging.getLogger(__name__)


_SEVERITY_EMOJI = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}

# Status codes considered successful by default
_DEFAULT_OK_STATUSES = {200, 201, 202, 204}


class WebhookChannel(BaseChannel):
    kind = "webhook"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        url = config.get("url")
        if not url:
            return SendResult(ok=False, error="webhook missing url")

        method = (config.get("method") or "POST").upper()
        content_type = config.get("content_type") or "application/json"
        body_template = config.get("body_template")
        headers = dict(config.get("headers") or {})
        headers.setdefault("Content-Type", content_type)
        # Stable idempotency key, identical across retries, so a destination
        # that honours it can dedup a replayed delivery (audit F23). Falls
        # back to the notification id when the manager didn't pass one.
        headers.setdefault("Idempotency-Key", idempotency_key or notif.id)

        # Inject auth header
        auth_kind = config.get("auth_kind")
        if auth_kind:
            auth_value = resolve_secret(config, "auth_value", "auth_value_ref")
            if not auth_value:
                return SendResult(ok=False, error="auth_kind set but no value resolved")
            if auth_kind == "bearer":
                headers["Authorization"] = f"Bearer {auth_value}"
            elif auth_kind == "basic":
                headers["Authorization"] = f"Basic {auth_value}"
            elif auth_kind == "header":
                # Caller supplies "X-Custom: value" form
                if ":" in auth_value:
                    h_name, _, h_val = auth_value.partition(":")
                    headers[h_name.strip()] = h_val.strip()
                else:
                    return SendResult(ok=False, error="auth_kind=header requires 'Name: value'")
            else:
                return SendResult(ok=False, error=f"unknown auth_kind: {auth_kind}")

        # Build body. With no custom template we serialize a dict through
        # json.dumps so the default body is always valid JSON regardless of
        # what the title/message contain (audit A18: text interpolation of
        # {title} between hand-written quotes broke on a quote/newline). A
        # custom template is still rendered as text — operators escape
        # embedded values with the `| jsonstr` filter.
        ctx = _build_template_ctx(notif)
        # Same value as the Idempotency-Key header, for receivers that want it
        # in the body (identical on every retry of this delivery).
        ctx["idempotency_key"] = idempotency_key or notif.id
        if body_template:
            try:
                body_str = rendering.render(body_template, ctx)
            except Exception as e:
                return SendResult(ok=False, error=f"body template error: {e}")
        else:
            body_str = _build_default_body(ctx)

        ok_statuses = config.get("expected_status")
        if isinstance(ok_statuses, int):
            ok_statuses = {ok_statuses}
        elif isinstance(ok_statuses, list):
            ok_statuses = set(ok_statuses)
        else:
            ok_statuses = _DEFAULT_OK_STATUSES

        # If JSON, validate it renders cleanly before connecting (the rendered
        # string is sent as-is as the request content).
        if content_type == "application/json":
            try:
                json.loads(body_str)
            except json.JSONDecodeError as e:
                return SendResult(
                    ok=False,
                    error=f"rendered body is not valid JSON: {e}",
                    response={"rendered_body": body_str[:300]},
                )

        # SSRF-safe send (A-04): screen every resolved address and pin the
        # connection to an approved IP, so a rebinding host can't slip a
        # metadata/link-local (or, when configured, private) target in between
        # the policy check and the connection.
        try:
            r = await _http.request(
                "webhook", method, url, content=body_str, headers=headers,
                timeout=float(config.get("timeout_sec") or 10),
                # httpx error text echoes the request URL, which may carry a
                # token in userinfo/query or the path itself (Slack/Discord) —
                # neutralize it before returning/storing it (R07 + audit A-06).
                clean=lambda text: _safe_err(url, text),
            )
        except _http.Failed as f:
            return f.result
        if r.status_code in ok_statuses:
                return SendResult(ok=True, response={"status": r.status_code})
        return SendResult(
            ok=False,
            # Redact the upstream body — stored on the delivery row, readable
            # with scope `read`, and could echo a credential (audit S-10).
            error=redact_url(f"HTTP {r.status_code}: {r.text[:200]}"),
            response={"status": r.status_code},
            # 429 / 503: the receiver asked us to wait — defer, don't count
            # it against the channel (Retry-After, default 60 s).
            retry_after=retry_after_or_default(r.headers.get("Retry-After"))
            if r.status_code in BACKPRESSURE_STATUSES else None,
        )

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        url = config.get("url")
        if not url:
            return {"reachable": False, "error": "no url configured"}
        # Best-effort HEAD probe, SSRF-safe (A-04): the connection is pinned to
        # a screened IP. Many webhook URLs reject HEAD, so 405 is still "up".
        return await _http.probe("HEAD", url, clean=lambda text: _safe_err(url, text))


def _safe_err(url: Any, msg: str) -> str:
    """Scrub the destination URL out of an error string (audit A-06).

    Replaces the exact configured ``url`` with its safe host-only display —
    catching a secret in the path that ``redact_url`` can't classify — then
    applies the general URL redaction for userinfo / query / provider tokens.
    """
    if isinstance(url, str) and url:
        msg = msg.replace(url, safe_url_display(url))
    return cast(str, redact_url(msg))


def _build_template_ctx(notif: Notification) -> dict[str, Any]:
    """Make every notification field available to the body template."""
    ctx: dict[str, Any] = {
        "title": notif.title,
        "message": notif.message,
        "severity": notif.severity,
        "severity_emoji": _SEVERITY_EMOJI.get(notif.severity, ""),
        "icon": notif.icon or "",
        "type": notif.type,
        "id": notif.id,
        "rule_id": notif.rule_id,
        "fired_at": notif.fired_at.isoformat() if hasattr(notif.fired_at, "isoformat") else str(notif.fired_at),
    }
    # Flatten vars_payload if it's a dict — gives rule-defined vars
    if isinstance(notif.vars_payload, dict):
        for k, v in notif.vars_payload.items():
            ctx.setdefault(k, v)
    return ctx


def _build_default_body(ctx: dict[str, Any]) -> str:
    """Default webhook body — built as a dict and serialized with
    json.dumps so it is always valid JSON (audit A18), no matter what the
    title/message/fired_at strings contain."""
    return json.dumps(
        {
            # Notification id so the receiver can dedup/correlate a replay
            # (audit F23) — the default body previously omitted it.
            "id": ctx.get("id"),
            "type": ctx.get("type"),
            "title": ctx.get("title"),
            "message": ctx.get("message"),
            "severity": ctx.get("severity"),
            "fired_at": ctx.get("fired_at"),
        },
        ensure_ascii=False,
        default=str,
    )
