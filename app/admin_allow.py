"""Admin-plane allowlist (``ALERTD_ADMIN_ALLOW_CIDRS``).

When set, only clients from these networks reach anything but the two
public doors — ``POST /v1/fire`` and ``POST /v1/inputs/{id}/webhook`` —
over HTTP and WebSocket alike: the admin UI and its API, sign-in, the API
reference, health, metrics and the live streams. A second layer behind the
proxy's private router (docs/DEPLOY.md), for a Klopot reachable some other
way (its published port, a misrouted hostname).

- **Default deny.** A request is public only when its method and routed
  path (``scope["path"]``, never the Host-derived URL) are exactly one of
  the two doors; everything else, paths that do not exist included, is the
  admin plane. ``/v1/fire/``, ``/V1/fire`` and ``/v1//fire`` are not the door.
- **The real client.** The address is ``real_client_ip`` — behind a trusted
  proxy, the client it forwarded. A service calling Klopot directly inside
  the Docker network (pv-stack-ui) is its own address: list that network too.
- **Before the body.** Pure ASGI and outside the body limit, so a refused
  caller cannot make Klopot buffer a body; inside the activity log, so the
  refusal is recorded (without a body: nobody was let in).
- **Empty = off**, as for every existing install.
"""
from __future__ import annotations

import json
import re

from starlette.types import ASGIApp, Receive, Scope, Send

from .config import get_settings
from .utils.client_ip import Network, in_networks, real_client_ip

_WEBHOOK = re.compile(r"/v1/inputs/[0-9]+/webhook")


def is_public(method: str, path: str) -> bool:
    """Whether ``method path`` is one of the two public doors."""
    return method == "POST" and (path == "/v1/fire" or _WEBHOOK.fullmatch(path) is not None)


class AdminAllowMiddleware:
    """Refuse the admin plane to clients outside ``networks``: 403 over HTTP,
    close 1008 before the WebSocket is accepted."""

    def __init__(self, app: ASGIApp, networks: tuple[Network, ...]) -> None:
        self.app = app
        self.networks = networks

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        if kind not in ("http", "websocket") or not self.networks:
            await self.app(scope, receive, send)
            return
        if kind == "http" and is_public(scope.get("method", ""), scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        if self._allowed(scope):
            await self.app(scope, receive, send)
            return
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": "Not allowed from this address"})
            return
        body = json.dumps({"error": {"code": "ADDRESS_NOT_ALLOWED",
                                     "message": "Not allowed from this address"}}).encode()
        await send({"type": "http.response.start", "status": 403, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
        ]})
        await send({"type": "http.response.body", "body": body})

    def _allowed(self, scope: Scope) -> bool:
        client = scope.get("client")
        headers = dict(scope.get("headers") or [])
        xff = headers.get(b"x-forwarded-for")
        ip = real_client_ip(client[0] if client else None, xff.decode("latin-1") if xff else None,
                            get_settings().trusted_proxy_cidr_list)
        return ip is not None and in_networks(ip, self.networks)
