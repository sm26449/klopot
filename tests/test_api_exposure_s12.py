"""S-12: /docs and /v1/metrics exposure is configurable and defaults closed on a
TLS/prod deploy (cookie_secure=true), open on the plain-HTTP local quickstart."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config import Settings


def _s(**kw):
    return Settings(**kw)


def test_docs_auto_follows_cookie_secure():
    assert _s(cookie_secure=True).docs_enabled_effective is False
    assert _s(cookie_secure=False).docs_enabled_effective is True


def test_metrics_auth_auto_follows_cookie_secure():
    assert _s(cookie_secure=True).metrics_require_auth_effective is True
    assert _s(cookie_secure=False).metrics_require_auth_effective is False


def test_explicit_override_wins():
    assert _s(cookie_secure=True, docs_enabled=True).docs_enabled_effective is True
    assert _s(cookie_secure=False, metrics_require_auth=True).metrics_require_auth_effective is True


async def test_metrics_guard_open_when_not_required(monkeypatch):
    from app.api.v1 import metrics as m
    monkeypatch.setattr(m, "get_settings", lambda: _s(cookie_secure=False))
    # No actor needed; the guard returns without raising.
    assert await m._metrics_guard(SimpleNamespace(), api_key=None, session=None) is None


async def test_metrics_guard_rejects_anonymous_when_required(monkeypatch):
    from app.api.v1 import metrics as m
    monkeypatch.setattr(m, "get_settings", lambda: _s(cookie_secure=True))
    req = SimpleNamespace(client=None, cookies={}, headers={}, state=SimpleNamespace())
    with pytest.raises(HTTPException) as ei:
        await m._metrics_guard(req, api_key=None, session=None)
    assert ei.value.status_code == 401
