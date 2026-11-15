"""F35: a configured inbound token must actually be enforced — auth_required
defaults to True when a token is set, so a token can't give false assurance
while unauthenticated posts are accepted. Explicit False opts out."""
from __future__ import annotations

from unittest.mock import AsyncMock

from app.inputs.webhook import WebhookInput


def _wh(config):
    return WebhookInput(name="w", config=config, on_value=AsyncMock())


def test_auth_required_defaults_true_when_token_configured():
    wh = _wh({"auth_token": "secret"})
    assert wh._auth_required is True
    assert wh.check_auth(None) is False
    assert wh.check_auth("wrong") is False
    assert wh.check_auth("secret") is True


def test_without_a_flag_a_token_is_required_and_none_means_closed():
    # Until 1.2 "no flag, no token" meant open to anyone (public-exposure
    # review); now a token is required unless auth_required is false, and an
    # input with neither rejects every post.
    wh = _wh({})
    assert wh._auth_required is True
    assert wh.check_auth(None) is False
    assert wh.check_auth("anything") is False


def test_explicit_auth_required_false_is_honored_even_with_token():
    wh = _wh({"auth_token": "secret", "auth_required": False})
    assert wh._auth_required is False
    assert wh.check_auth(None) is True


def test_explicit_auth_required_true_without_token_rejects_all():
    wh = _wh({"auth_required": True})
    assert wh._auth_required is True
    assert wh.check_auth(None) is False
