"""SSRF-safe outbound HTTP with connect-time IP pinning (audit A-04).

The egress policy in :mod:`app.utils.egress` is only sound if the IP it screens
is the IP the request actually connects to. A plain ``httpx`` request re-resolves
the host itself, so a hostname that resolves to an allowed address during the
check and a forbidden one at connect time (DNS rebinding) defeats it.

:func:`safe_request` closes that gap: it resolves the host, screens **every**
resolved address, and then connects to an approved one **by IP** while keeping
the original ``Host`` header and setting ``sni_hostname`` to the real host, so
TLS SNI and certificate validation still run against the hostname (verified: a
cert is validated against the SNI name, not the pinned IP). Redirects are never
followed, so each hop can't bypass the screen.

Private/loopback destinations stay allowed unless ``block_private`` is set —
internal delivery (sms-gateway, mosquitto on the Docker network) is a supported,
documented policy choice. Metadata/link-local is always refused.
"""
from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..config import get_settings
from .egress import _default_resolver, screen_ip


class EgressBlocked(Exception):
    """Raised when a destination fails the egress policy at screen time."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ResponseTooLarge(Exception):
    """Raised when an upstream response exceeds the decompressed byte cap."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _pin_url(url: str, ip: str) -> tuple[str, str, str]:
    """Return ``(connect_url, host_header, sni_hostname)`` for pinning.

    ``connect_url`` targets ``ip`` directly (v6 bracketed), preserving scheme,
    any userinfo, port, path, query and fragment. ``host_header`` and
    ``sni_hostname`` carry the original hostname so routing, SNI and certificate
    validation are unaffected by connecting to the literal address.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port
    ip_lit = f"[{ip}]" if ":" in ip else ip

    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += f":{parts.password}"
        userinfo += "@"
    netloc = f"{userinfo}{ip_lit}"
    if port is not None:
        netloc += f":{port}"

    connect_url = urlunsplit(
        (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
    )
    host_header = host if port is None else f"{host}:{port}"
    return connect_url, host_header, host


async def screen_and_pick_ip(
    url: str,
    *,
    block_private: bool = False,
    resolver: Callable[[str], list[str]] | None = None,
) -> str:
    """Resolve ``url``'s host and return one approved IP to connect to.

    Raises :class:`EgressBlocked` if the host is missing, does not resolve,
    resolves to a malformed address, or **any** resolved address fails the
    policy (a dual-stack answer with one forbidden address is refused whole).
    """
    resolve = resolver or _default_resolver
    try:
        parts = urlsplit(url)
    except ValueError as e:
        raise EgressBlocked("unparseable url") from e
    host = parts.hostname
    if not host:
        raise EgressBlocked("missing host in url")

    addrs = await asyncio.to_thread(resolve, host)
    if not addrs:
        raise EgressBlocked(f"could not resolve host {host!r} for egress screening")

    approved: list[str] = []
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError as e:
            raise EgressBlocked(
                f"invalid resolved address {a!r} for host {host!r}"
            ) from e
        reason = screen_ip(ip, block_private)
        if reason:
            raise EgressBlocked(reason)
        approved.append(a)
    # Every address passed; pin the first.
    return approved[0]


async def safe_request(
    method: str,
    url: str,
    *,
    timeout: float,  # noqa: ASYNC109 — plain httpx timeout value, not a cancel scope
    block_private: bool = False,
    resolver: Callable[[str], list[str]] | None = None,
    headers: dict[str, str] | None = None,
    max_response_bytes: int | None = None,
    client: httpx.AsyncClient | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Screen ``url`` and issue ``method`` against the pinned, approved IP.

    Keeps the original ``Host`` header and pins TLS SNI to the real hostname, so
    certificate validation is unchanged. Never follows redirects. The response
    is read with a **decompressed** byte cap (``max_response_bytes``, default
    ``settings.max_response_bytes``), so a huge or compression-bomb upstream
    body can't exhaust memory (audit A-08). Raises :class:`EgressBlocked` if the
    destination fails the policy, :class:`ResponseTooLarge` past the cap; httpx
    errors propagate unchanged. ``client`` may be supplied (e.g. for tests).
    """
    ip = await screen_and_pick_ip(url, block_private=block_private, resolver=resolver)
    connect_url, host_header, sni = _pin_url(url, ip)

    merged = dict(headers or {})
    merged["Host"] = host_header
    extensions = {"sni_hostname": sni}
    cap = max_response_bytes if max_response_bytes is not None else get_settings().max_response_bytes

    own_client = client is None
    c = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    try:
        request = c.build_request(
            method, connect_url, headers=merged, extensions=extensions, **kwargs
        )
        response = await c.send(request, stream=True)
        try:
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > cap:
                    raise ResponseTooLarge(
                        f"upstream response exceeds {cap} bytes"
                    )
        finally:
            await response.aclose()
        # Attach the capped, already-decoded body so callers can use
        # ``.text`` / ``.json()`` without re-reading the (closed) stream.
        response._content = bytes(body)
        return response
    finally:
        if own_client:
            await c.aclose()
