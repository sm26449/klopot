"""Adapter test kit (roadmap §5): a new HTTP channel's test is ~40 lines.

    from tests.channels._kit import FakeHTTP, notification, reply, assert_http_contract

    async def test_contract(monkeypatch):
        http = FakeHTTP.install(monkeypatch, my_module)        # replaces my_module.safe_request
        await assert_http_contract(MyChannel(), {"token": "s3cret", …}, http, secrets=["s3cret"])

``assert_http_contract`` checks what every adapter must do: a 2xx is
``ok=True``; a 5xx, a timeout and an egress block are ``ok=False`` with an
error; no secret value ever appears in an error string. Adapter-specific
behaviour (payload shape, priorities, provider_ref) stays in the adapter's
own test, using ``http.calls`` and ``reply(...)``.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import ModuleType
from typing import Any

import httpx

from app.channels.base import Notification
from app.utils.safe_http import EgressBlocked


def notification(**overrides: Any) -> Notification:
    base: dict[str, Any] = dict(
        id="ntf_kit_1", type="kit_test", severity="critical", icon="🧪",
        title="Kit title ăîș", message="Kit message", fired_at=datetime.now(UTC),
        vars_payload={}, rule_id=None,
    )
    base.update(overrides)
    return Notification(**base)


class _Reply:
    def __init__(self, status_code: int, payload: Any, text: str) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


def reply(status_code: int = 200, json: Any = None, text: str = "") -> _Reply:
    return _Reply(status_code, json, text)


class FakeHTTP:
    """Stands in for ``safe_request`` in an adapter module."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.replies: list[Any] = [reply(200, {})]

    @classmethod
    def install(cls, monkeypatch: Any, module: ModuleType) -> FakeHTTP:
        fake = cls()
        monkeypatch.setattr(module, "safe_request", fake)
        return fake

    def will(self, *responses: Any) -> FakeHTTP:
        """Next responses, in order (an Exception instance is raised)."""
        self.replies = list(responses)
        return self

    async def __call__(self, method: str, url: str, **kw: Any) -> Any:
        self.calls.append({"method": method, "url": url, **kw})
        nxt = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


async def assert_http_contract(
    channel: Any, config: dict[str, Any], http: FakeHTTP, *,
    secrets: list[str] = (), ok_reply: Any = None,  # type: ignore[assignment]
) -> None:
    notif = notification()

    http.will(ok_reply or reply(200, {}))
    res = await channel.send(notif, config, idempotency_key="idem-1")
    assert res.ok, f"2xx must be ok, got {res.error}"

    failures = [
        reply(503, {}, text=f"upstream down {' '.join(secrets)}"),
        httpx.ConnectTimeout("timed out"),
        httpx.ConnectError(f"connection refused to https://user:{'x'.join(secrets) or 'p'}@host/"),
        EgressBlocked("destination blocked by egress policy"),
    ]
    for failure in failures:
        http.will(failure)
        res = await channel.send(notif, config, idempotency_key="idem-1")
        assert not res.ok, f"{failure!r} must fail"
        assert res.error, f"{failure!r} must carry an error"
        for secret in secrets:
            assert secret not in res.error, f"secret leaked in error for {failure!r}: {res.error}"
