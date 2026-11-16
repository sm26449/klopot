"""The scheme the client used, behind a TLS-terminating proxy.

Traefik (or any reverse proxy) ends TLS and talks plain HTTP to Klopot, so
the ASGI scope says ``http``: a trailing-slash redirect then sent an HTTPS
client to ``http://…`` (review F13), and ``request.url`` was wrong. This
layer sets the scope's scheme from ``X-Forwarded-Proto`` — only when the
direct peer is in ``ALERTD_TRUSTED_PROXY_CIDRS``, the list that already
decides whose ``X-Forwarded-For`` counts — so there is one trust setting,
not a second one in gunicorn (``FORWARDED_ALLOW_IPS``) that can disagree.

Pure ASGI, outermost: everything inside, the redirects included, sees it.
"""
from __future__ import annotations

from typing import Any

from .utils.client_ip import forwarded_scheme

_WS = {"http": "ws", "https": "wss"}


class ForwardedProtoMiddleware:
    def __init__(self, app: Any, *, trusted_cidrs: list[str]) -> None:
        self.app = app
        self.trusted_cidrs = trusted_cidrs

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] in ("http", "websocket") and self.trusted_cidrs:
            client = scope.get("client")
            proto = next((v.decode("latin-1") for k, v in scope.get("headers") or [] if k == b"x-forwarded-proto"), None)
            scheme = forwarded_scheme(client[0] if client else None, proto, self.trusted_cidrs)
            if scheme:
                scope = {**scope, "scheme": scheme if scope["type"] == "http" else _WS[scheme]}
        await self.app(scope, receive, send)
