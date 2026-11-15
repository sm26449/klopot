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


async def test_health_exposes_background_components(client: AsyncClient):
    body = (await client.get("/v1/health")).json()
    comps = body["components"]
    for name in ("engine", "scheduler", "delivery", "outbox"):
        assert name in comps, f"missing health component {name}"


async def test_health_always_200(client: AsyncClient):
    # Even with essential tasks down in-process, /health is informational.
    assert (await client.get("/v1/health")).status_code == 200


async def test_readiness_503_when_essential_down(client: AsyncClient):
    # In the in-process test app the rule engine / delivery worker are not
    # started, so readiness must fail hard.
    r = await client.get("/v1/health/ready")
    assert r.status_code == 503
    assert _essential_down_from_body(r.json())


def _essential_down_from_body(body) -> list[str]:
    return [n for n, c in body["components"].items()
            if n in {"database", "engine", "delivery"} and c["status"] == "down"]
