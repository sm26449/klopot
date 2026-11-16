"""The client's scheme behind a TLS proxy, and no server banner (review F13).

Behind Traefik the ASGI scope says http: a trailing-slash redirect sent an
HTTPS client to http://… . X-Forwarded-Proto now sets the scheme — only from
a peer in ALERTD_TRUSTED_PROXY_CIDRS, the list that already decides whose
X-Forwarded-For counts.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.utils.client_ip import forwarded_scheme

TRUSTED = ["172.20.0.0/16"]


@pytest.mark.parametrize(("peer", "proto", "expected"), [
    ("172.20.0.5", "https", "https"),
    ("172.20.0.5", "HTTPS", "https"),
    ("172.20.0.5", "http", "http"),
    ("172.20.0.5", "https, http", "http"),    # the last value is the trusted proxy's own
    ("172.20.0.5", "http, https", "https"),
    ("172.20.0.5", "gopher", None),
    ("172.20.0.5", None, None),
    ("203.0.113.9", "https", None),           # not a trusted proxy: its claim is ignored
    (None, "https", None),
])
def test_forwarded_scheme_trusts_only_the_proxies(peer, proto, expected):
    assert forwarded_scheme(peer, proto, TRUSTED) == expected


def test_no_trusted_proxies_means_no_forwarded_scheme():
    assert forwarded_scheme("172.20.0.5", "https", []) is None


async def _redirect_location(monkeypatch, trusted: str, proto: str | None) -> str:
    monkeypatch.setenv("ALERTD_TRUSTED_PROXY_CIDRS", trusted)
    get_settings.cache_clear()
    try:
        from app.main import create_app

        app = create_app()
        headers = {"x-forwarded-proto": proto} if proto else {}
        # httpx's ASGI transport connects from 127.0.0.1.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://klopot.test") as c:
            r = await c.get("/v1/health/", headers=headers)
        assert r.status_code == 307
        return r.headers["location"]
    finally:
        get_settings.cache_clear()


async def test_a_redirect_keeps_https_behind_a_trusted_proxy(monkeypatch):
    assert (await _redirect_location(monkeypatch, "127.0.0.1/32", "https")).startswith("https://klopot.test/v1/health")


async def test_an_untrusted_peer_cannot_choose_the_scheme(monkeypatch):
    assert (await _redirect_location(monkeypatch, "172.20.0.0/16", "https")).startswith("http://klopot.test/")


def test_the_image_worker_sends_no_server_banner_and_leaves_proxies_to_klopot():
    from app.worker import KlopotWorker

    assert KlopotWorker.CONFIG_KWARGS["server_header"] is False
    assert KlopotWorker.CONFIG_KWARGS["proxy_headers"] is False
