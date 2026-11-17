"""F32: health must surface essential background-task liveness, and a
readiness probe must fail (503) when an essential component is down."""
from __future__ import annotations

from httpx import AsyncClient

from app.api.v1.health import (
    ComponentHealth,
    _essential_down,
    _overall,
)


def _c(status):
    return ComponentHealth(status=status)


def test_overall_is_worst_status():
    assert _overall({"a": _c("ok"), "b": _c("ok")}) == "ok"
    assert _overall({"a": _c("ok"), "b": _c("degraded")}) == "degraded"
    assert _overall({"a": _c("down"), "b": _c("degraded")}) == "down"


def test_essential_down_only_flags_essentials():
    comps = {
        "database": _c("ok"), "engine": _c("down"),
        "delivery": _c("ok"), "scheduler": _c("down"),  # not essential
        "mqtt": _c("down"),  # not essential
    }
    assert _essential_down(comps) == ["engine"]


def test_essential_down_empty_when_all_essentials_ok():
    comps = {"database": _c("ok"), "engine": _c("ok"), "delivery": _c("ok"),
             "mqtt": _c("down"), "scheduler": _c("down")}
    assert _essential_down(comps) == []


async def test_health_exposes_background_components(read_client: AsyncClient):
    body = (await read_client.get("/v1/health")).json()
    comps = body["components"]
    for name in ("engine", "scheduler", "delivery", "outbox"):
        assert name in comps, f"missing health component {name}"


async def test_health_always_200(client: AsyncClient):
    # Even with essential tasks down in-process, /health is informational.
    assert (await client.get("/v1/health")).status_code == 200


async def test_readiness_503_when_essential_down(client: AsyncClient, read_client: AsyncClient):
    # In the in-process test app the rule engine / delivery worker are not
    # started, so readiness must fail hard — for every caller; only a reader
    # learns which component is down.
    r = await read_client.get("/v1/health/ready")
    assert r.status_code == 503
    assert _essential_down_from_body(r.json())
    anonymous = await client.get("/v1/health/ready")
    assert anonymous.status_code == 503
    assert anonymous.json() == {"status": "down", "service": "alertd"}


def _essential_down_from_body(body) -> list[str]:
    return [n for n, c in body["components"].items()
            if n in {"database", "engine", "delivery"} and c["status"] == "down"]


def test_a_stuck_engine_is_down_although_its_task_is_alive(monkeypatch):
    # IP-01: the task is alive but its loop has not come round — no rule is
    # evaluated. Readiness must see it (and so must Kurier's watchdog ping).
    from app.api.v1 import health
    from app.core.engine import RuleEngine

    class Stuck:
        def is_alive(self):
            return True

        def stalled_for(self):
            return RuleEngine.STALL_SEC + 5

    monkeypatch.setattr("app.core.engine.get_engine", lambda: Stuck())
    comp = health._engine_component()
    assert comp.status == "down" and comp.code == "engine_stalled"
    assert _essential_down({"engine": comp}) == ["engine"]


async def test_a_turning_engine_reports_its_last_round():
    from app.core.engine import RuleEngine

    engine = RuleEngine()
    assert engine.stalled_for() == 0.0
    engine._last_turn = __import__("time").monotonic() - 7
    assert 6.5 < engine.stalled_for() < 60
