"""A-04: SSRF egress hardening — mapped-address normalization, resolution
rejection, and connect-time IP pinning.

Covers the egress classifier fixes (``egress``), the pinning layer
(``safe_http``), and that the webhook/http-poll paths refuse a rebinding
target through the shared layer.
"""
from __future__ import annotations

import ipaddress

import httpx
import pytest

from app.utils import safe_http
from app.utils.egress import egress_blocked, normalize_ip, screen_ip
from app.utils.safe_http import (
    EgressBlocked,
    _pin_url,
    safe_request,
    screen_and_pick_ip,
)

META_V4 = "169.254.169.254"
META_MAPPED = "::ffff:169.254.169.254"


def _resolve_to(*ips):
    return lambda host: list(ips)


# ── Mapped-address normalization (the core A-04 classifier fix) ───────


def test_mapped_metadata_normalizes_to_ipv4():
    assert normalize_ip(ipaddress.ip_address(META_MAPPED)) == ipaddress.ip_address(META_V4)


def test_6to4_embedded_ipv4_normalized():
    # 2002:a9fe:a9fe:: embeds 169.254.169.254
    ip = ipaddress.ip_address("2002:a9fe:a9fe::")
    assert normalize_ip(ip) == ipaddress.ip_address(META_V4)


def test_screen_ip_blocks_plain_and_mapped_metadata():
    assert screen_ip(ipaddress.ip_address(META_V4)) is not None
    # The bypass: an IPv4-mapped v6 address embedding the metadata IPv4 must be
    # blocked. (Python's own ``is_link_local`` for the mapped form flipped between
    # 3.12 patch releases, so we don't assert on it — only that we block it.)
    mapped = ipaddress.ip_address(META_MAPPED)
    assert screen_ip(mapped) is not None


def test_screen_ip_private_policy():
    v4 = ipaddress.ip_address("10.0.0.5")
    assert screen_ip(v4) is None                     # allowed by default
    assert screen_ip(v4, block_private=True) is not None
    # mapped private is also caught under strict policy
    assert screen_ip(ipaddress.ip_address("::ffff:10.0.0.5"), block_private=True) is not None


def test_egress_blocked_catches_mapped_metadata():
    reason = egress_blocked("http://sneaky.example/x", resolver=_resolve_to(META_MAPPED))
    assert reason is not None
    assert "metadata" in reason


def test_egress_blocked_rejects_empty_and_invalid_resolution():
    assert egress_blocked("http://h/x", resolver=_resolve_to()) is not None       # empty
    assert egress_blocked("http://h/x", resolver=_resolve_to("not-an-ip")) is not None


# ── _pin_url construction ────────────────────────────────────────────


def test_pin_url_ipv4_with_port():
    cu, host, sni = _pin_url("https://hooks.example.com:8443/p?q=1", "93.184.216.34")
    assert cu == "https://93.184.216.34:8443/p?q=1"
    assert host == "hooks.example.com:8443"
    assert sni == "hooks.example.com"


def test_pin_url_default_port_host_header_has_no_port():
    cu, host, sni = _pin_url("http://hooks.example.com/p", "93.184.216.34")
    assert cu == "http://93.184.216.34/p"
    assert host == "hooks.example.com"


def test_pin_url_ipv6_is_bracketed():
    cu, _h, _s = _pin_url("https://h.example/p", "2606:4700::1")
    assert cu == "https://[2606:4700::1]/p"


def test_pin_url_preserves_userinfo():
    cu, host, _s = _pin_url("https://u:p@h.example/p", "1.2.3.4")
    assert cu == "https://u:p@1.2.3.4/p"
    assert host == "h.example"


# ── screen_and_pick_ip ───────────────────────────────────────────────


async def test_pick_ip_blocks_metadata():
    with pytest.raises(EgressBlocked):
        await screen_and_pick_ip("http://h/x", resolver=_resolve_to(META_V4))


async def test_pick_ip_blocks_mapped_metadata():
    with pytest.raises(EgressBlocked):
        await screen_and_pick_ip("http://h/x", resolver=_resolve_to(META_MAPPED))


async def test_pick_ip_blocks_dual_stack_if_any_forbidden():
    # A rebinding/dual-stack answer with one allowed and one forbidden address
    # is refused whole — we must not connect to the "good" one and leave the
    # bad one reachable on retry.
    with pytest.raises(EgressBlocked):
        await screen_and_pick_ip("http://h/x", resolver=_resolve_to("93.184.216.34", META_V4))


async def test_pick_ip_rejects_unresolvable():
    with pytest.raises(EgressBlocked):
        await screen_and_pick_ip("http://h/x", resolver=_resolve_to())


async def test_pick_ip_returns_first_approved():
    ip = await screen_and_pick_ip("http://h/x", resolver=_resolve_to("93.184.216.34", "1.1.1.1"))
    assert ip == "93.184.216.34"


# ── safe_request pins the connection ─────────────────────────────────


async def test_safe_request_pins_to_ip_and_preserves_host_and_sni():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["host"] = request.headers.get("Host")
        captured["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text="ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        r = await safe_request(
            "GET", "https://hooks.example.com:8443/p?q=1", timeout=5,
            resolver=_resolve_to("93.184.216.34"), client=client,
        )
    assert r.status_code == 200
    assert captured["url"] == "https://93.184.216.34:8443/p?q=1"   # connected by IP
    assert captured["host"] == "hooks.example.com:8443"            # Host preserved
    assert captured["sni"] == "hooks.example.com"                  # TLS SNI/cert host


async def test_safe_request_raises_before_connecting_on_block():
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        with pytest.raises(EgressBlocked):
            await safe_request(
                "GET", "http://h/x", timeout=5,
                resolver=_resolve_to(META_MAPPED), client=client,
            )
    assert called["n"] == 0   # never connected


# ── Channel wiring: a rebinding target is refused through the layer ───


async def test_webhook_send_refuses_metadata_target(monkeypatch):
    from datetime import datetime

    from app.channels.base import Notification
    from app.channels.webhook import WebhookChannel

    monkeypatch.setattr(safe_http, "_default_resolver", _resolve_to(META_MAPPED))
    notif = Notification(
        id="n1", type="t", severity="info", icon=None, title="t", message="m",
        fired_at=datetime(2026, 11, 12, 0, 0),
    )
    res = await WebhookChannel().send(notif, {"url": "https://sneaky.example/hook"})
    assert res.ok is False
    assert "metadata" in (res.error or "")
