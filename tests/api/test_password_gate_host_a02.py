"""A-02: the forced-password-change gate must decide on the routed ASGI
path, never ``request.url.path`` — the latter is reconstructed from the
attacker-controlled Host header, so a crafted Host could make a config
write read as an allowed password-change path and bypass the gate.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from app.auth import CSRF_HEADER, SessionContext, _enforce_browser_write_rules


class _Headers:
    def __init__(self, d: dict[str, str]) -> None:
        self._d = {k.lower(): v for k, v in d.items()}

    def get(self, k: str, default=None):
        return self._d.get(k.lower(), default)


class _URL:
    def __init__(self, path: str) -> None:
        self.path = path


class _Req:
    """Enough of a Starlette Request for the write-rules gate."""

    def __init__(self, *, method: str, path: str, headers: dict[str, str], url_path: str) -> None:
        self.method = method
        self.scope = {"path": path}          # what the router matched
        self.headers = _Headers(headers)
        self.url = _URL(url_path)            # Host-reconstructed; untrusted


def _ctx(*, must_change: bool) -> SessionContext:
    now = datetime(2026, 1, 1)
    return SessionContext(
        session_id=1, user_id=1, username="admin", csrf_token="tok",
        must_change_password=must_change,
        created_at=now, last_seen_at=now, expires_at=now,
    )


def test_gate_blocks_write_even_when_url_path_is_spoofed_to_allowed():
    # Routed to a config write, but url.path spoofed to an allowed path.
    req = _Req(
        method="POST", path="/v1/channels",
        headers={"host": "testserver", CSRF_HEADER: "tok"},
        url_path="/v1/auth/password",
    )
    with pytest.raises(HTTPException) as ei:
        _enforce_browser_write_rules(req, _ctx(must_change=True))
    assert ei.value.status_code == 403
    assert ei.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"


def test_gate_allows_the_real_password_change_route():
    # Genuinely routed to the allowed path → the gate must let it through,
    # regardless of what url.path says.
    req = _Req(
        method="POST", path="/v1/auth/password",
        headers={"host": "testserver", CSRF_HEADER: "tok"},
        url_path="/v1/channels",
    )
    _enforce_browser_write_rules(req, _ctx(must_change=True))  # must not raise


def test_malformed_host_is_rejected():
    req = _Req(
        method="POST", path="/v1/channels",
        headers={"host": "evil/../x@attacker", CSRF_HEADER: "tok"},
        url_path="/v1/channels",
    )
    with pytest.raises(HTTPException) as ei:
        _enforce_browser_write_rules(req, _ctx(must_change=False))
    assert ei.value.status_code == 400
    assert ei.value.detail["code"] == "BAD_HOST"


def test_clean_host_with_port_is_accepted():
    # A normal Host (with a port) must not trip the guard.
    req = _Req(
        method="POST", path="/v1/auth/password",
        headers={"host": "alerts.example:8443", CSRF_HEADER: "tok"},
        url_path="/v1/auth/password",
    )
    _enforce_browser_write_rules(req, _ctx(must_change=True))  # must not raise
