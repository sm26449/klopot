"""Kurier watches Klopot (ADR-0003): the ping, its health verdict, and the
two episodes Klopot raises from the answer."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core import kurier_watchdog as wd
from app.core.health import ComponentHealth
from app.db.models import Channel, ChannelKind, Incident, NotificationLog
from tests._db import fresh
from tests.channels._kit import FakeHTTP, reply

HEALTHY = {"database": ComponentHealth(status="ok"), "engine": ComponentHealth(status="ok"),
           "delivery": ComponentHealth(status="ok"), "outbox": ComponentHealth(status="ok")}
MODEM_OK = {"kurier": "ok", "modem": {"registered": True, "signal_strength": -71, "sim_state": "ready",
                                      "operator": "Orange"}, "watchdog": {"state": "up"}}


# ── Pure parts ────────────────────────────────────────────────────────


@pytest.mark.parametrize(("channel", "name"), [
    ("sms_main", "klopot-sms_main"), ("SMS Kurier!", "klopot-sms-kurier"), ("---", "klopot-sms"),
    ("x" * 80, "klopot-" + "x" * 57),
])
def test_watchdog_names_fit_kuriers_alphabet(channel, name):
    assert wd.watchdog_name(channel) == name


def test_verdict_is_the_readiness_rule_plus_a_stuck_outbox():
    assert wd.verdict(HEALTHY) == ("ok", "")
    stuck = {**HEALTHY, "engine": ComponentHealth(status="down", detail="rule engine stuck for 200s")}
    assert wd.verdict(stuck) == ("fail", "engine: rule engine stuck for 200s")
    backlog = {**HEALTHY, "outbox": ComponentHealth(status="degraded", detail="3 delivery(ies) overdue >120s")}
    assert wd.verdict(backlog)[0] == "fail"
    assert wd.verdict({**HEALTHY, "mqtt": ComponentHealth(status="down")}) == ("ok", ""), "not essential"


def test_ping_body():
    assert wd.ping_body({}, "ok", "") == {"timeout_sec": 180, "status": "ok"}
    body = wd.ping_body({"watchdog_timeout_sec": 600, "watchdog_to": "+40700, +40701"}, "fail", "engine: stuck")
    assert body == {"timeout_sec": 600, "status": "fail", "detail": "engine: stuck", "to": ["+40700", "+40701"]}


# ── The loop against a database ───────────────────────────────────────


@pytest.fixture
async def kurier(db_session, monkeypatch):
    """The built-in templates, a watched kurier channel, a healthy Klopot."""
    from scripts.seed import seed_builtin_templates, seed_default_channels

    await seed_default_channels(db_session)
    await seed_builtin_templates(db_session)
    channel = Channel(name="sms_main", kind=ChannelKind.sms, enabled=True, config={
        "provider": "kurier", "phone": "+40700", "kurier_url": "http://kurier:5080", "api_key": "k-s3cret",
        "watchdog": True})
    db_session.add_all([channel, Channel(name="sms_other", kind=ChannelKind.sms, enabled=True, config={
        "provider": "http", "phone": "+1", "url": "http://gw/send", "watchdog": True})])
    await db_session.commit()

    async def healthy():
        return HEALTHY

    monkeypatch.setattr(wd, "collect_components", healthy)
    return channel


async def _incident(db_session, key):
    await fresh(db_session)
    return (await db_session.execute(select(Incident).where(Incident.source_key == key))).scalar_one_or_none()


async def test_only_a_kurier_channel_with_the_watchdog_on_is_pinged(monkeypatch, kurier):
    http = FakeHTTP.install(monkeypatch, wd).will(reply(200, MODEM_OK))
    await wd.KurierWatchdog().tick()
    [call] = http.calls
    assert call["method"] == "POST" and call["url"] == "http://kurier:5080/api/watchdogs/klopot-sms_main/ping"
    assert call["headers"] == {"X-API-Key": "k-s3cret"}
    assert call["json"] == {"timeout_sec": 180, "status": "ok"}


async def test_no_watched_channel_means_no_request(monkeypatch, db_session):
    http = FakeHTTP.install(monkeypatch, wd)
    await wd.KurierWatchdog().tick()
    assert http.calls == []


async def test_kurier_unreachable_after_three_failed_pings_and_back(monkeypatch, db_session, kurier):
    import httpx

    http = FakeHTTP.install(monkeypatch, wd).will(httpx.ConnectError("refused"))
    watchdog = wd.KurierWatchdog()
    key = f"kurier:{kurier.id}:unreachable"
    for _ in range(2):
        await watchdog.tick()
    assert await _incident(db_session, key) is None, "two misses are not an outage"
    await watchdog.tick()
    opened = await _incident(db_session, key)
    assert opened is not None and opened.resolved_at is None and opened.template_type == "kurier_unreachable"

    http.will(reply(200, MODEM_OK))
    await watchdog.tick()
    closed = await _incident(db_session, key)
    assert closed.resolved_at is not None
    types = set((await db_session.execute(select(NotificationLog.type))).scalars())
    assert {"kurier_unreachable", "kurier_reachable"} <= types


async def test_a_404_says_kurier_has_no_watchdogs(monkeypatch, kurier):
    FakeHTTP.install(monkeypatch, wd).will(reply(404, {"detail": "Not Found"}))
    result = await wd.ping(kurier.config, "klopot-sms_main", "ok", "")
    assert not result.ok and "without watchdogs" in result.error


async def test_the_modem_off_the_network_is_an_episode(monkeypatch, db_session, kurier):
    off = {**MODEM_OK, "modem": {"registered": False, "signal_strength": None, "sim_state": "not inserted"}}
    http = FakeHTTP.install(monkeypatch, wd).will(reply(200, off))
    watchdog = wd.KurierWatchdog()
    key = f"kurier:{kurier.id}:modem"
    await watchdog.tick()
    opened = await _incident(db_session, key)
    assert opened is not None and opened.template_type == "kurier_modem_down"
    http.will(reply(200, MODEM_OK))
    await watchdog.tick()
    assert (await _incident(db_session, key)).resolved_at is not None


async def test_a_missing_key_is_reported_without_a_request(monkeypatch, kurier):
    http = FakeHTTP.install(monkeypatch, wd)
    result = await wd.ping({**kurier.config, "api_key": None}, "klopot-sms_main", "ok", "")
    assert not result.ok and "api_key" in result.error and http.calls == []


async def test_a_refused_ping_says_why(monkeypatch, kurier):
    FakeHTTP.install(monkeypatch, wd).will(reply(422, {"detail": "to: +4x is not a phone number"}))
    result = await wd.ping(kurier.config, "klopot-sms_main", "ok", "")
    assert not result.ok and result.error == "HTTP 422: to: +4x is not a phone number"
