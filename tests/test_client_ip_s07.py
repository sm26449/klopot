"""S-07: behind a trusted reverse proxy the real client IP must come from
X-Forwarded-For, so per-IP login throttling keys on the client, not the proxy —
without trusting a spoofed XFF from a direct (untrusted) connection.

Uses documentation TEST-NET ranges (RFC 5737) for the proxy subnet so the logic
is exercised without embedding site-private RFC1918 literals."""
from __future__ import annotations

import pytest

from app.config import Settings
from app.utils.client_ip import parse_trusted_proxies, real_client_ip

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


# ── The trusted list fails closed (public-exposure review, stage 0) ─────

@pytest.mark.parametrize("spec", ["nope", "198.51.100.0/24, 10.0.0.300", "0.0.0.0/0", "::/0", "198.51.100.0/24,0.0.0.0/0"])
def test_an_invalid_or_catch_all_trusted_proxy_stops_startup(spec):
    """A typo used to be logged and skipped, silently turning 'trust traefik'
    into 'trust nothing' (every client shares the proxy's address) — and a /0
    let any client pick its address. Both now refuse to start."""
    with pytest.raises(ValueError, match="trusted proxy"):
        parse_trusted_proxies(spec)
    with pytest.raises(ValueError, match="trusted proxy"):
        Settings(trusted_proxy_cidrs=spec)


def test_a_valid_list_parses_once_and_blank_entries_are_ignored():
    nets = parse_trusted_proxies("198.51.100.0/24, ,2001:db8::/32,")
    assert [str(n) for n in nets] == ["198.51.100.0/24", "2001:db8::/32"]
    assert parse_trusted_proxies("198.51.100.0/24, ,2001:db8::/32,") is nets, "cached, not re-parsed per request"
    assert Settings(trusted_proxy_cidrs="").trusted_proxy_cidr_list == []


def test_an_ipv4_mapped_peer_is_the_ipv4_address_it_maps():
    # A dual-stack listener reports an IPv4 proxy as ::ffff:198.51.100.1.
    assert real_client_ip("::ffff:198.51.100.1", CLIENT, TRUSTED) == CLIENT
