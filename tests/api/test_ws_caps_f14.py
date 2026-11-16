"""Live streams are bounded (review F14).

Each stream holds a queue and costs a JSON encode per update; nothing capped
how many one caller opened. The registry refuses past MAX_PER_IDENTITY for
one session or API key and past MAX_TOTAL altogether. The handlers reserve
before accepting: a stream without room is closed (1013) and never served,
and a place is released however the stream ends.
"""
from __future__ import annotations

import pytest

from app.api.v1 import state as state_api
from app.auth import Actor
from app.core import ws_registry
from app.core.ws_registry import MAX_PER_IDENTITY, StreamLimitReached, WSRegistry


class FakeWS:
    def __init__(self, fail_accept: bool = False) -> None:
        self.accepted = False
        self.closed: list[int] = []
        self.fail_accept = fail_accept

    async def accept(self) -> None:
        if self.fail_accept:
            raise RuntimeError("client went away")
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed.append(code)


@pytest.fixture
def registry(monkeypatch) -> WSRegistry:
    reg = WSRegistry()
    monkeypatch.setattr(ws_registry, "_registry", reg)
    return reg


def test_one_session_or_key_holds_at_most_its_share(registry):
    for _ in range(MAX_PER_IDENTITY):
        registry.register(object(), session_id=1, user_id=1)
    with pytest.raises(StreamLimitReached, match="per session or key"):
        registry.register(object(), session_id=1, user_id=1)
    registry.register(object(), session_id=2, user_id=1)          # another tab's session
    for _ in range(MAX_PER_IDENTITY):
        registry.register(object(), key_id=9)
    with pytest.raises(StreamLimitReached):
        registry.register(object(), key_id=9)


def test_the_process_holds_at_most_max_total(registry, monkeypatch):
    monkeypatch.setattr(ws_registry, "MAX_TOTAL", 3)
    for i in range(3):
        registry.register(object(), key_id=i)
    with pytest.raises(StreamLimitReached, match="at most 3 live streams"):
        registry.register(object(), key_id=99)


def test_a_closed_stream_frees_its_place(registry):
    handles = [registry.register(object(), key_id=5) for _ in range(MAX_PER_IDENTITY)]
    registry.unregister(handles[0])
    registry.register(object(), key_id=5)


async def test_a_stream_without_room_is_closed_before_it_is_accepted(registry):
    actor = Actor(kind="api_key", id=5, name="k", scopes=frozenset({"read"}))
    for _ in range(MAX_PER_IDENTITY):
        registry.register(object(), key_id=5)
    ws = FakeWS()
    assert await state_api._accept_registered(ws, actor) is None
    assert ws.accepted is False
    assert ws.closed == [1013]


async def test_a_failed_accept_releases_the_place(registry):
    actor = Actor(kind="api_key", id=5, name="k", scopes=frozenset({"read"}))
    with pytest.raises(RuntimeError):
        await state_api._accept_registered(FakeWS(fail_accept=True), actor)
    assert len(registry) == 0
