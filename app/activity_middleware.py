"""ASGI middleware that records every HTTP request in the activity log.

Policy (docs/ACTIVITY_LOG.md): every request is recorded with method, route,
status, duration, actor, client IP, user agent and trace id; the first
matching activity rule (admin UI → Activity → Rules) can shorten its
retention, ignore it (counted only) or change what is kept of the bodies.
Admin-UI static files are not recorded. Recording never delays or fails the
request: the row goes to a background writer.
"""
from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from .config import Settings, get_settings
from .core.activity import (
    ERROR_RESPONSE_LIMIT,
    FIRE_BODY_LIMIT,
    WEBHOOK_BODY_LIMIT,
    record_request,
    redact_body,
)
from .core.activity_rules import Rule, get_rule_cache
from .utils.client_ip import real_client_ip
from .utils.redact import redact_url
from .utils.time import utc_now

# Static admin UI assets: a page load fetches dozens; they say nothing about callers.
_SKIP_PREFIXES = ("/admin/", "/favicon")
_NEVER_BODY = ("/v1/auth/",)        # carries passwords / session tokens
# Whole configurations (YAML or JSON, literal secrets included when the import
# is refused): the masking of JSON keys cannot be trusted with them.
_NEVER_REQUEST_BODY = (*_NEVER_BODY, "/v1/config/", "/v1/packs/")
_CAPTURE_LIMIT = WEBHOOK_BODY_LIMIT  # never buffer more of a body than we could store


def _is_ingress(path: str) -> bool:
    return path.startswith("/v1/inputs/") and path.endswith("/webhook")


def _want_request_body(mode: str, method: str, path: str, status: int, authenticated: bool) -> int:
    """How many bytes of the request body to keep (0 = none).

    Never the body of a caller who did not get in, whatever the rule says: an
    anonymous client could otherwise make us store 4 KiB (64 KiB on an inbound
    endpoint) per request, for the whole retention period. Inbound endpoints
    authenticate with their own token: there ``authenticated`` means the
    endpoint marked the request as let in (``request.state.inbound_ok``) — not
    "any status but 401/403/404", which kept bodies answered 400, 413, 422 or
    503 before the token was checked (review K10).
    """
    if path.startswith(_NEVER_REQUEST_BODY) or method in ("GET", "HEAD", "OPTIONS") or not get_settings().activity_log_bodies:
        return 0
    if not authenticated:
        return 0
    limit = WEBHOOK_BODY_LIMIT if _is_ingress(path) else FIRE_BODY_LIMIT
    if mode == "never":
        return 0
    if mode == "always":
        return limit
    if mode == "errors":
        return limit if status >= 400 else 0
    # auto: inbound alerts / payloads always, other writes on error only
    return limit if (_is_ingress(path) or path == "/v1/fire" or status >= 400) else 0


def _want_response_body(mode: str, path: str, status: int) -> int:
    if path.startswith(_NEVER_BODY) or not get_settings().activity_log_bodies:
        return 0
    if mode == "never":
        return 0
    if mode == "always":
        return FIRE_BODY_LIMIT
    if mode == "errors":
        return ERROR_RESPONSE_LIMIT if status >= 400 else 0
    return ERROR_RESPONSE_LIMIT if (status >= 400 or _is_ingress(path) or path == "/v1/fire") else 0


def route_template(path: str, params: dict[str, Any] | None, *, matched: bool) -> str:
    """``/v1/inputs/3/webhook`` → ``/v1/inputs/{input_id}/webhook`` (for grouping).

    Built from the real path and the matched path parameters, because the
    route object in the scope is relative to whichever nested router matched.
    """
    if not matched:
        return "(no route)"
    segments = path.split("/")
    for name, value in (params or {}).items():
        for i, seg in enumerate(segments):
            if seg == str(value):
                segments[i] = "{" + name + "}"
                break
    return "/".join(segments)


def _keep_days(rule: Rule | None, status: int, let_in: bool, settings: Settings) -> int:
    """How long a request's row is kept: the matching rule's ``keep_days``;
    else, for a refused caller who was not let in (any 4xx — a wrong key, a
    guessed path, a locked login), ``activity_refused_days`` (review F5:
    anonymous guesses are cheap, months of rows are not); else
    ``log_retention_days``."""
    if rule is not None and rule.keep_days:
        return rule.keep_days
    if not let_in and 400 <= status < 500:
        return min(settings.activity_refused_days, settings.log_retention_days)
    return settings.log_retention_days


class ActivityLogMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["path"].startswith(_SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        ts = utc_now()
        req_chunks: list[bytes] = []
        req_size = 0
        resp_chunks: list[bytes] = []
        resp_size = 0
        status_box = {"status": 500}

        async def recv() -> Any:
            nonlocal req_size
            message = await receive()
            if message.get("type") == "http.request" and req_size < _CAPTURE_LIMIT:
                body = message.get("body", b"")
                req_chunks.append(body[: _CAPTURE_LIMIT - req_size])
                req_size += len(body)
            return message

        async def snd(message: Any) -> None:
            nonlocal resp_size
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
            elif message["type"] == "http.response.body" and resp_size < _CAPTURE_LIMIT:
                body = message.get("body", b"")
                resp_chunks.append(body[: _CAPTURE_LIMIT - resp_size])
                resp_size += len(body)
            await send(message)

        try:
            await self.app(scope, recv, snd)
        finally:
            try:
                await self._record(scope, ts, started, status_box["status"], b"".join(req_chunks), b"".join(resp_chunks))
            except Exception:  # the log must never break a request
                import logging
                logging.getLogger(__name__).debug("activity log: request not recorded", exc_info=True)

    async def _record(self, scope: dict[str, Any], ts: Any, started: float, status: int,
                      req_body: bytes, resp_body: bytes) -> None:
        settings = get_settings()
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        peer = (scope.get("client") or (None,))[0]
        ip = real_client_ip(peer, headers.get("x-forwarded-for"), settings.trusted_proxy_cidr_list)
        actor = (scope.get("state") or {}).get("actor")
        actor_name = getattr(actor, "name", None)
        cache = get_rule_cache()
        rule: Rule | None = await cache.match(method=method, path=path, status=status, actor=actor_name, ip=ip)
        if rule is not None and rule.action == "ignore":
            cache.count_hit(rule, ip)
            return
        if rule is not None:
            cache.count_hit(rule, ip)
        route = route_template(path, scope.get("path_params"), matched=scope.get("route") is not None)
        let_in = (scope.get("state") or {}).get("inbound_ok") if _is_ingress(path) else actor is not None
        keep_days = _keep_days(rule, status, bool(let_in), settings)
        req_limit = _want_request_body(rule.request_body if rule else "auto", method, path, status,
                                       authenticated=bool(let_in))
        resp_limit = _want_response_body(rule.response_body if rule else "auto", path, status)
        from .logging_setup import trace_id_var

        record_request({
            "ts": ts, "method": method[:8], "route": route[:191],
            # The query string can carry a token (?token=…) — redact like any URL.
            "path": redact_url(path + ("?" + scope["query_string"].decode("latin-1") if scope.get("query_string") else ""))[:500],
            "status": status, "duration_ms": int((time.monotonic() - started) * 1000),
            "actor_kind": getattr(actor, "kind", None), "actor_name": actor_name[:64] if actor_name else None,
            "api_key_id": getattr(actor, "id", None) if getattr(actor, "kind", None) == "api_key" else None,
            "client_ip": ip[:45] if ip else None, "user_agent": (headers.get("user-agent") or "")[:255] or None,
            "trace_id": trace_id_var.get(),
            "request_body": redact_body(req_body, req_limit) if req_limit else None,
            "response_body": redact_body(resp_body, resp_limit) if resp_limit else None,
            "expires_at": ts + timedelta(days=keep_days), "rule_id": rule.id if rule else None,
        })
