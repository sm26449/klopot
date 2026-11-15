"""Outbound egress policy for admin-configured URLs (audit R06, A-04).

Webhook / HTTP-poll targets are operator-configured and internal destinations
(the Docker network, an SMS gateway, an MQTT broker) are a supported use case, so this
does NOT block private ranges by default. It always blocks cloud-metadata and
link-local addresses (never a legitimate target), and can additionally block
private/loopback ranges when ``block_private`` is set.

Two classes of bypass this guards against (A-04):

- **Mapped-address evasion.** An IPv4-mapped (``::ffff:169.254.169.254``),
  6to4 or IPv4-compatible IPv6 address embeds a forbidden IPv4 address while
  presenting as a v6 object whose ``is_link_local`` is ``False``. Every address
  is normalised to its embedded IPv4 before classification.
- **Resolve-then-connect TOCTOU (DNS rebinding).** Checking the host here and
  then letting the HTTP client re-resolve and connect can hit a different IP.
  Connect-time pinning lives in :mod:`app.utils.safe_http`, which screens each
  resolved address with :func:`screen_ip` and connects only to an approved one.
  This module's :func:`egress_blocked` remains a pre-flight check.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

# IIDS v6 endpoint lives in a unique-local prefix, so pin it explicitly on top
# of the link-local check.
_IMDS_V6 = ipaddress.ip_address("fd00:ec2::254")
# NAT64 well-known prefix: the low 32 bits carry an embedded IPv4, so a NAT64
# address can reach 169.254.169.254 (metadata) or a private host while reading
# as a plain global v6 — normalise it to that IPv4 before classifying (S-08).
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
# Carrier-grade NAT / shared address space — not flagged by is_private, but never
# a legitimate internet target; treated as private under strict egress (S-08).
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
# Cloud metadata services outside link-local: Alibaba Cloud's lives inside
# CGNAT, so the strict-only CGNAT rule missed it (review K24). Always blocked.
_METADATA = frozenset({ipaddress.ip_address("100.100.100.200")})

IPAddr = ipaddress.IPv4Address | ipaddress.IPv6Address


def _default_resolver(host: str) -> list[str]:
    try:
        return [info[4][0] for info in socket.getaddrinfo(host, None)]
    except OSError:
        return []


def normalize_ip(ip: IPAddr) -> IPAddr:
    """Collapse an IPv6 address that *embeds* an IPv4 address to that IPv4.

    IPv4-mapped (``::ffff:a.b.c.d``), IPv4-compatible (``::a.b.c.d``) and 6to4
    (``2002:xxyy:zzww::``) forms all carry a routable IPv4 address that must be
    classified as that IPv4 — otherwise a forbidden v4 target slips through as a
    v6 object whose ``is_link_local`` / ``is_private`` flags read ``False``.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip.sixtofour is not None:
            return ip.sixtofour
        if ip in _NAT64:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        # IPv4-compatible ``::a.b.c.d`` (deprecated) — low 32 bits are the v4.
        if ip.version == 6 and int(ip) >> 32 == 0 and not ip.is_loopback and int(ip) != 0:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def screen_ip(ip: IPAddr, block_private: bool = False) -> str | None:
    """Return a block reason for a single resolved address, else ``None``.

    Always blocks cloud-metadata / link-local; additionally blocks
    private/loopback when ``block_private`` is set. Mapped/embedded v6 forms are
    normalised first so a forbidden embedded IPv4 cannot evade the check.
    """
    ip = normalize_ip(ip)
    if ip.is_link_local or ip == _IMDS_V6 or ip in _METADATA:
        return f"blocked egress to metadata/link-local address {ip}"
    # Never a legitimate HTTP target, in any mode (S-08).
    if ip.is_multicast or ip.is_unspecified:
        return f"blocked egress to multicast/unspecified address {ip}"
    if block_private and (ip.is_private or ip.is_loopback or ip.is_reserved or ip in _CGNAT):
        return f"blocked egress to private/loopback address {ip} (strict egress)"
    return None


def egress_blocked(
    url: str,
    block_private: bool = False,
    resolver: Callable[[str], list[str]] = _default_resolver,
) -> str | None:
    """Pre-flight check: return a reason if ``url`` must not be fetched, else
    ``None``. Blocks by resolved IP so a hostname that maps to a forbidden
    address is caught too.

    This is advisory — the authoritative decision is made at connect time by
    :mod:`app.utils.safe_http`, which pins the screened IP. A host that fails to
    resolve is rejected here (A-04): a connection could still succeed via a
    resolver that disagrees, so an unresolvable target is not implicitly safe.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "unparseable url"
    host = parts.hostname
    if not host:
        return "missing host in url"

    addrs = resolver(host)
    if not addrs:
        return f"could not resolve host {host!r} for egress screening"

    for a in addrs:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            # A resolver returning a non-address string is a malformed result,
            # not a safe one — refuse rather than skip it.
            return f"invalid resolved address {a!r} for host {host!r}"
        reason = screen_ip(ip, block_private)
        if reason:
            return reason
    return None


async def broker_blocked(host: str, port: int) -> str | None:
    """A reason to refuse a non-HTTP broker connection (MQTT), else None
    (review K24). Only what is never a legitimate target — metadata,
    link-local, multicast, unspecified: brokers normally live on the private
    network, so ``block_private_egress`` does not apply. A host that does not
    resolve is left to the client to fail on (there is no pinning here, so
    refusing it would add nothing). DNS is resolved off the event loop."""
    import asyncio

    try:
        addrs = [str(ipaddress.ip_address(host))]
    except ValueError:
        addrs = await asyncio.to_thread(_default_resolver, host)
    for a in addrs:
        try:
            reason = screen_ip(ipaddress.ip_address(a))
        except ValueError:
            continue
        if reason:
            return reason
    return None
