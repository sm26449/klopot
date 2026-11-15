"""Resolve the real client IP, honoring X-Forwarded-For from trusted proxies.

Behind a reverse proxy (traefik) every request's TCP peer is the proxy, so
per-IP login throttling would key on the proxy and be useless (audit S-07).
When the peer is a configured trusted proxy, trust the X-Forwarded-For chain it
appended and take the rightmost entry that is NOT itself a trusted proxy — the
address the trusted edge actually saw. Rightmost-non-trusted defeats spoofing: a
client can prepend fake XFF entries, but everything to the right was added by
infrastructure we trust.
"""
from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)


def _networks(cidrs: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for c in cidrs:
        try:
            nets.append(ipaddress.ip_network(c, strict=False))
        except ValueError:
            logger.warning("ignoring invalid trusted_proxy CIDR %r", c)
    return nets


def _in_nets(ip: str, nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)


def real_client_ip(peer: str | None, xff: str | None, trusted_cidrs: list[str]) -> str | None:
    """The real client IP given the direct peer and the X-Forwarded-For header.

    Returns ``peer`` unchanged unless ``peer`` is inside a trusted-proxy CIDR and
    an XFF header is present, in which case it returns the rightmost XFF entry
    that is not itself a trusted proxy (the peer when every entry is).
    """
    if not (peer and xff and trusted_cidrs):
        return peer
    nets = _networks(trusted_cidrs)
    if not nets or not _in_nets(peer, nets):
        return peer
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    for cand in reversed(parts):
        if not _in_nets(cand, nets):
            return cand
    # Every hop is "trusted" (a CIDR as wide as 0.0.0.0/0): the leftmost entry
    # is the client's own claim, so trust none of them — use the peer (K15).
    return peer
