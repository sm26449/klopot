"""Resolve the real client IP, honoring X-Forwarded-For from trusted proxies.

Behind a reverse proxy (traefik) every request's TCP peer is the proxy, so
per-IP login throttling would key on the proxy and be useless (audit S-07).
When the peer is a configured trusted proxy, trust the X-Forwarded-For chain it
appended and take the rightmost entry that is NOT itself a trusted proxy — the
address the trusted edge actually saw. Rightmost-non-trusted defeats spoofing: a
client can prepend fake XFF entries, but everything to the right was added by
infrastructure we trust.

The trusted list is parsed once (``parse_trusted_proxies``, cached) and the
same parser validates ``ALERTD_TRUSTED_PROXY_CIDRS`` at startup: an entry that
is not a network, or one that trusts every address, stops the service instead
of being skipped. Every per-client control — login lockout, the wrong-key
budget, the activity log and any address allowlist — depends on this list, so
a typo must not silently turn into "trust nothing" or "trust everything".
"""
from __future__ import annotations

import ipaddress
from functools import lru_cache

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=16)
def parse_trusted_proxies(spec: str) -> tuple[Network, ...]:
    """The networks of a comma-separated CIDR list (blank entries ignored).

    Raises ``ValueError`` naming the entry for one that is not an address or
    network, and for a /0 — trusting every address as a proxy would let any
    client choose its own address with X-Forwarded-For."""
    nets: list[Network] = []
    for raw in spec.split(","):
        entry = raw.strip()
        if not entry:
            continue
        try:
            net = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            raise ValueError(f"trusted proxy {entry!r} is not an IP address or CIDR") from None
        if net.prefixlen == 0:
            raise ValueError(f"trusted proxy {entry!r} trusts every address; list the proxies' own networks")
        nets.append(net)
    return tuple(nets)


def _in_nets(ip: str, nets: tuple[Network, ...]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # An IPv4-mapped IPv6 peer (::ffff:10.0.0.5) is the IPv4 address it maps.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return any(addr in n for n in nets)


def real_client_ip(peer: str | None, xff: str | None, trusted_cidrs: list[str]) -> str | None:
    """The real client IP given the direct peer and the X-Forwarded-For header.

    Returns ``peer`` unchanged unless ``peer`` is inside a trusted-proxy CIDR and
    an XFF header is present, in which case it returns the rightmost XFF entry
    that is not itself a trusted proxy (the peer when every entry is).
    """
    if not (peer and xff and trusted_cidrs):
        return peer
    nets = parse_trusted_proxies(",".join(trusted_cidrs))
    if not nets or not _in_nets(peer, nets):
        return peer
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    for cand in reversed(parts):
        if not _in_nets(cand, nets):
            return cand
    # Every hop is "trusted": the leftmost entry is the client's own claim, so
    # trust none of them — use the peer (K15).
    return peer
