"""S-07: behind a trusted reverse proxy the real client IP must come from
X-Forwarded-For, so per-IP login throttling keys on the client, not the proxy —
without trusting a spoofed XFF from a direct (untrusted) connection.

Uses documentation TEST-NET ranges (RFC 5737) for the proxy subnet so the logic
is exercised without embedding site-private RFC1918 literals."""
from __future__ import annotations

from app.utils.client_ip import real_client_ip

# Stand-in "trusted proxy subnet" — any range works; TEST-NET keeps it generic.
TRUSTED = ["198.51.100.0/24"]
PROXY = "198.51.100.1"      # a peer inside the trusted subnet
CLIENT = "203.0.113.5"      # the real external client


def test_no_trusted_proxy_uses_peer():
    # No trusted CIDRs configured → ignore XFF entirely.
    assert real_client_ip(PROXY, CLIENT, []) == PROXY


def test_untrusted_peer_ignores_xff():
    # A direct client could forge XFF; only trust it from a trusted proxy.
    assert real_client_ip("8.8.8.8", "1.1.1.1", TRUSTED) == "8.8.8.8"


def test_trusted_proxy_uses_rightmost_nontrusted():
    assert real_client_ip(PROXY, CLIENT, TRUSTED) == CLIENT


def test_spoofed_prepend_is_defeated():
    # Client prepends a fake entry; the proxy appends the real one on the right.
    assert real_client_ip(PROXY, f"192.0.2.6, {CLIENT}", TRUSTED) == CLIENT


def test_chained_trusted_proxies_skip_to_real_client():
    # client, edge-proxy, inner-proxy → rightmost non-trusted is the client.
    assert real_client_ip("198.51.100.2", f"{CLIENT}, {PROXY}", TRUSTED) == CLIENT


def test_missing_values_return_peer():
    assert real_client_ip(None, CLIENT, TRUSTED) is None
    assert real_client_ip(PROXY, None, TRUSTED) == PROXY
