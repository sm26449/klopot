"""S-06: a WebSocket ``?api_key=`` reaches the uvicorn access log, whose handler
bypasses the root redacting filter. The access filter must redact the key while
leaving the record's arg tuple intact (uvicorn's AccessFormatter unpacks it)."""
from __future__ import annotations

import logging

from app.logging_setup import _AccessRedactingFilter


def _record(msg, args):
    return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, msg, args, None)


def test_redacts_api_key_in_tuple_args_without_breaking_unpacking():
    f = _AccessRedactingFilter()
    rec = _record(
        '%s - "%s %s HTTP/%s" %s',
        ("1.2.3.4:5", "GET", "/v1/ws/log?api_key=SUPERSECRET", "1.1", 101),
    )
    assert f.filter(rec) is True
    # Arg tuple stays a 5-tuple so uvicorn's AccessFormatter can still unpack it.
    assert isinstance(rec.args, tuple) and len(rec.args) == 5
    out = rec.getMessage()
    assert "SUPERSECRET" not in out
    assert "api_key=<redacted>" in out
    assert "1.2.3.4" in out and out.endswith("101")


def test_redacts_token_in_dict_args():
    f = _AccessRedactingFilter()
    rec = _record("%(request)s", {"request": "GET /x?token=abc123", "status": 200})
    assert f.filter(rec) is True
    assert "abc123" not in rec.getMessage()


def test_redacts_plain_message_without_args():
    f = _AccessRedactingFilter()
    rec = _record("connect wss://h/ws?api_key=zzz", None)
    assert f.filter(rec) is True
    assert "zzz" not in rec.getMessage()


def test_non_credential_record_is_untouched():
    f = _AccessRedactingFilter()
    rec = _record('%s - "%s" %s', ("1.2.3.4", "GET /v1/health", 200))
    assert f.filter(rec) is True
    assert rec.getMessage() == '1.2.3.4 - "GET /v1/health" 200'
