"""R06: outbound egress policy — always block cloud-metadata/link-local;
optionally block private/loopback. Internal destinations stay allowed by
default (the Docker network is a supported use case)."""
from __future__ import annotations

from app.utils.egress import egress_blocked


def _resolve_to(ip):
    return lambda host: [ip]


def test_metadata_endpoint_always_blocked():
    reason = egress_blocked("http://169.254.169.254/latest/meta-data",
                            resolver=_resolve_to("169.254.169.254"))
    assert reason is not None
    assert "metadata" in reason


def test_link_local_always_blocked():
    reason = egress_blocked("http://host.internal/x", resolver=_resolve_to("169.254.10.5"))
    assert reason is not None


def test_private_allowed_by_default():
    # The container network (10.20.x) must stay reachable by default.
    assert egress_blocked("http://sms-gw:5080/send",
                          resolver=_resolve_to("10.20.0.9")) is None


def test_private_blocked_when_strict():
    reason = egress_blocked("http://sms-gw:5080/send", block_private=True,
                            resolver=_resolve_to("10.20.0.9"))
    assert reason is not None
    assert "private" in reason


def test_loopback_blocked_when_strict():
    reason = egress_blocked("http://localhost/x", block_private=True,
                            resolver=_resolve_to("127.0.0.1"))
    assert reason is not None


def test_public_address_allowed():
    assert egress_blocked("https://hooks.example.com/x",
                          resolver=_resolve_to("93.184.216.34")) is None


def test_missing_host_rejected():
    assert egress_blocked("not-a-url") is not None


def test_unresolvable_host_rejected():
    # A-04: an unresolvable target is NOT implicitly safe — a resolver that
    # disagrees at connect time could still reach a forbidden address, so the
    # pre-flight check refuses it rather than passing it through.
    reason = egress_blocked("http://nope.invalid/x", resolver=lambda h: [])
    assert reason is not None
    assert "resolve" in reason


# ── S-08: NAT64 / CGNAT / multicast gaps ───────────────────────────────

def test_nat64_embedding_metadata_is_blocked():
    # 64:ff9b::a9fe:a9fe embeds 169.254.169.254 (cloud metadata) but reads as a
    # plain global v6 — it must be normalised and blocked (audit S-08).
    reason = egress_blocked("http://h/x", resolver=_resolve_to("64:ff9b::a9fe:a9fe"))
    assert reason is not None and "metadata" in reason


def test_nat64_embedding_private_blocked_only_when_strict():
    url, res = "http://h/x", _resolve_to("64:ff9b::0a00:0001")  # 192.0.2.1
    assert egress_blocked(url, resolver=res) is None
    assert egress_blocked(url, block_private=True, resolver=res) is not None


def test_nat64_embedding_public_is_allowed():
    # NAT64 to a real public v4 is a legitimate transition path.
    assert egress_blocked("http://h/x", resolver=_resolve_to("64:ff9b::0808:0808")) is None


def test_multicast_always_blocked():
    for ip in ("224.0.0.1", "ff02::1"):
        assert egress_blocked("http://h/x", resolver=_resolve_to(ip)) is not None


def test_unspecified_always_blocked():
    assert egress_blocked("http://h/x", resolver=_resolve_to("0.0.0.0")) is not None


def test_cgnat_blocked_only_when_strict():
    url, res = "http://h/x", _resolve_to("100.64.0.1")
    assert egress_blocked(url, resolver=res) is None
    assert egress_blocked(url, block_private=True, resolver=res) is not None
