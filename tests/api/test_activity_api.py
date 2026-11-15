"""Activity log (docs/ACTIVITY_LOG.md): every request recorded with who / where /
status, rules that shorten, ignore (counted) or shape what is kept, delivery
attempts with their HTTP exchange, state-change events, retention."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from app.core.activity import get_activity_writer, redact_body
from app.db.models import ActivityRule, ApiRequest, DeliveryAttempt, SystemEvent
from app.utils.time import utc_now


def _h(key):
    return {"X-API-Key": key}


async def _flush():
    await get_activity_writer().flush()


async def _requests(db_client, key, **params):
    await _flush()
    r = await db_client.get("/v1/activity/requests", headers=_h(key), params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


async def test_every_request_is_recorded_with_who_where_and_status(db_client, admin_key):
    await db_client.get("/v1/templates", headers=_h(admin_key))
    await db_client.get("/v1/templates", headers={"X-API-Key": "alertd_wrong_key_xxxxxxxxxxxx"})
    await db_client.get("/v1/no-such-thing", headers=_h(admin_key))
    rows = await _requests(db_client, admin_key)
    by_status = {(r["route"], r["status"]): r for r in rows}
    ok = by_status[("/v1/templates", 200)]
    assert ok["actor_name"] and ok["actor_kind"] == "api_key" and ok["method"] == "GET" and ok["duration_ms"] >= 0
    assert by_status[("/v1/templates", 401)]["actor_name"] is None
    assert ("(no route)", 404) in by_status
    assert all(r["route"] != "/v1/activity/requests" or r["status"] == 200 for r in rows)


async def test_bodies_follow_the_policy_and_never_leak_secrets(db_client, admin_key, db_session):
    await db_client.post("/v1/fire", headers=_h(admin_key), json={"type": "unknown_x", "context": {"password": "hunter2", "v": 1}})
    await db_client.post("/v1/auth/login", json={"username": "admin", "password": "not-the-password"})
    await db_client.get("/v1/templates?token=supersecret", headers=_h(admin_key))
    await _flush()
    rows = {r.route: r for r in (await db_session.execute(select(ApiRequest))).scalars()}
    fire = rows["/v1/fire"]
    assert '"v": 1' in fire.request_body and "hunter2" not in fire.request_body and "<redacted>" in fire.request_body
    assert fire.response_body  # /v1/fire keeps the response
    login = rows["/v1/auth/login"]
    assert login.request_body is None and "not-the-password" not in (login.response_body or "")
    assert "supersecret" not in rows["/v1/templates"].path
    assert rows["/v1/templates"].request_body is None  # reads carry no body


async def test_request_detail_with_bodies_needs_admin(db_client, admin_key, db_session):
    await db_client.post("/v1/fire", headers=_h(admin_key), json={"type": "t_x", "context": {}})
    row = (await _requests(db_client, admin_key, route="/v1/fire"))[0]
    assert row["has_request_body"] is True and "request_body" not in row
    detail = (await db_client.get(f"/v1/activity/requests/{row['id']}", headers=_h(admin_key))).json()
    assert detail["request_body"]
    read_key = (await db_client.post("/v1/api_keys", headers=_h(admin_key), json={"name": "viewer", "scopes": ["read"]})).json()["key"]
    assert (await db_client.get(f"/v1/activity/requests/{row['id']}", headers=_h(read_key))).status_code == 403


async def test_ignore_rule_keeps_nothing_but_counts(db_client, admin_key):
    h = _h(admin_key)
    rule = (await db_client.post("/v1/activity/rules", headers=h, json={
        "name": "no reads of templates", "match_method": "get", "match_path": "/v1/templates*", "action": "ignore"})).json()
    assert rule["match_method"] == "GET"
    for _ in range(3):
        await db_client.get("/v1/templates", headers=h)
    rows = await _requests(db_client, admin_key, route="/v1/templates")
    assert rows == []
    src = (await db_client.get("/v1/activity/sources", headers=h)).json()
    ignored = next(i for i in src["ignored"] if i["rule_id"] == rule["id"])
    assert ignored["hits"] == 3 and ignored["last_hit_at"] and ignored["pattern"] == "GET /v1/templates*"


async def test_keep_days_rule_shortens_retention_and_retention_deletes(db_client, admin_key, db_session):
    h = _h(admin_key)
    await db_client.post("/v1/activity/rules", headers=h, json={
        "name": "short", "match_path": "/v1/channels", "keep_days": 1, "position": 1})
    await db_client.get("/v1/channels", headers=h)
    await _flush()
    row = (await db_session.execute(select(ApiRequest).where(ApiRequest.route == "/v1/channels"))).scalars().first()
    assert timedelta(hours=23) < row.expires_at - row.ts <= timedelta(days=1)
    from app.core.retention import RetentionService

    row_id = row.id
    row.expires_at = utc_now() - timedelta(minutes=1)
    await db_session.commit()
    await RetentionService()._sweep()
    from tests._db import fresh
    await fresh(db_session)
    assert (await db_session.execute(select(ApiRequest).where(ApiRequest.id == row_id))).scalar_one_or_none() is None


async def test_rule_preview_counts_recent_matches(db_client, admin_key):
    h = _h(admin_key)
    for _ in range(2):
        await db_client.get("/v1/channels", headers=h)
    await _flush()
    p = (await db_client.post("/v1/activity/rules/preview", headers=h, json={"name": "x", "match_path": "/v1/channels"})).json()
    assert p["matched"] == 2 and len(p["examples"]) == 2
    bad = await db_client.post("/v1/activity/rules", headers=h, json={"name": "x", "match_status": "abc"})
    assert bad.status_code == 422


async def test_channel_test_is_an_attempt_with_its_exchange(db_client, admin_key):
    h = _h(admin_key)
    ch = (await db_client.post("/v1/channels", headers=h, json={
        "name": "hook", "kind": "webhook", "config": {"url": "https://hooks.example.com/x"}})).json()
    resp = MagicMock(status_code=200, headers={"content-type": "application/json", "x-secret-header": "no"}, text="{}")
    resp.json.return_value = {}

    async def fake_send(method, url, **kw):
        from app.core.activity import note_exchange
        note_exchange(method=method, url=url, status=200, duration_ms=5, request_body=kw.get("content"),
                      response_body=b'{"ok": true}', response_headers=resp.headers)
        return resp

    with patch("app.channels._http.safe_request", AsyncMock(side_effect=fake_send)):
        assert (await db_client.post(f"/v1/channels/{ch['id']}/test", headers=h)).json()["ok"] is True
    await _flush()
    items = (await db_client.get("/v1/activity/attempts", headers=h, params={"channel": "hook"})).json()["items"]
    a = items[0]
    assert a["kind"] == "test" and a["outcome"] == "sent" and a["http_status"] == 200
    ex = a["exchange"][0]
    assert ex["url"].startswith("https://hooks.example.com") and ex["response_body"] == '{"ok": true}'
    assert ex["response_headers"] == {"content-type": "application/json"}  # other headers never kept
    read_key = (await db_client.post("/v1/api_keys", headers=h, json={"name": "viewer2", "scopes": ["read"]})).json()["key"]
    ro = (await db_client.get("/v1/activity/attempts", headers=_h(read_key), params={"channel": "hook"})).json()["items"][0]
    assert "response_body" not in ro["exchange"][0]


async def test_breaker_transitions_are_events(db_session):
    from app.channels.circuit_breaker import CircuitBreaker

    b = CircuitBreaker(threshold=2, open_sec=60)
    for _ in range(3):
        await b.record_failure("gw", "HTTP 500")
    await b.record_success("gw")
    await _flush()
    events = [e.event for e in (await db_session.execute(select(SystemEvent).order_by(SystemEvent.id))).scalars()]
    assert events == ["breaker_open", "breaker_closed"]


def test_redact_body_masks_secret_keys_and_urls_and_trims():
    out = redact_body({"api_key": "k", "nested": {"bot_token": "t", "auth_value_ref": "NAME"}, "url": "https://u:p@h/x?token=s"}, 4096)
    assert '"api_key": "<redacted>"' in out and '"bot_token": "<redacted>"' in out and '"auth_value_ref": "NAME"' in out
    assert "u:p@" not in out and "token=s" not in out
    assert redact_body("x" * 100, 10).endswith("[90 more bytes]")
    assert redact_body(b"", 10) is None
    assert redact_body(bytes([0xff, 0xfe, 0x00, 0x81]) * 10, 4096) == "[binary, 40 bytes]"


async def test_writer_never_blocks_and_counts_drops():
    from app.core.activity import ActivityWriter

    w = ActivityWriter(max_queue=2)
    for _ in range(5):
        w.submit("event", {"ts": utc_now(), "source_kind": "input", "source_name": "x", "event": "connected"})
    assert w.dropped == 3


async def test_activity_rule_crud_is_audited(db_client, admin_key, db_session):
    h = _h(admin_key)
    rid = (await db_client.post("/v1/activity/rules", headers=h, json={"name": "a", "match_path": "/x"})).json()["id"]
    assert (await db_client.patch(f"/v1/activity/rules/{rid}", headers=h, json={"action": "ignore"})).json()["action"] == "ignore"
    assert (await db_client.delete(f"/v1/activity/rules/{rid}", headers=h)).status_code == 204
    assert (await db_session.execute(select(ActivityRule).where(ActivityRule.id == rid))).scalar_one_or_none() is None
    actions = [a["action"] for a in (await db_client.get("/v1/audit", headers=h, params={"resource_kind": "activity_rule"})).json()["items"]]
    assert sorted(actions) == ["activity_rule.create", "activity_rule.delete", "activity_rule.update"]
    assert DeliveryAttempt is not None  # imported table exists


async def test_ignored_hits_reach_the_table_with_nothing_else_queued(db_client, admin_key, db_session):
    """An ignore rule queues no row; its counter must still be written."""
    h = _h(admin_key)
    rid = (await db_client.post("/v1/activity/rules", headers=h, json={
        "name": "quiet", "match_path": "/v1/schedules*", "action": "ignore"})).json()["id"]
    await _flush()                                   # write the rule-create request itself
    await db_client.get("/v1/schedules", headers=h)  # ignored → only a counter
    writer = get_activity_writer()
    assert writer._q().empty()
    assert await writer.flush() == 0                 # no rows …
    from tests._db import fresh
    await fresh(db_session)
    rule = (await db_session.execute(select(ActivityRule).where(ActivityRule.id == rid))).scalar_one()
    assert rule.hits == 1 and rule.last_hit_at is not None   # … but the counter is written


# ── Secrets never reach the stored rows (audit P02, P03, P12) ─────────────────


def test_form_body_masks_provider_credentials():
    """P02: Pushover posts a form; its app token and user key are fields of it."""
    out = redact_body(b"token=APPTOKEN123&user=USERKEY456&title=Disk+full&priority=1", 4096)
    assert "APPTOKEN123" not in out and "USERKEY456" not in out
    assert out == "token=<redacted>&user=<redacted>&title=Disk+full&priority=1"
    assert redact_body("just some = text here", 4096) == "just some = text here"


def test_registered_secret_fields_and_header_values_are_masked():
    """P12: `user_key` holds no marker word; custom headers carry API keys."""
    out = redact_body({"config": {"user_key": "UK1", "username": "mq", "url": "https://h",
                                  "headers": {"DD-API-KEY": "ddsecret", "X-Trace": "t"}}}, 4096)
    assert "UK1" not in out and "ddsecret" not in out and '"mq"' not in out
    assert '"DD-API-KEY": "<redacted>"' in out and '"X-Trace": "<redacted>"' in out


def test_exchange_keeps_only_the_host_of_a_destination():
    """P03: a webhook path can be the credential (Slack, Discord, Home Assistant)."""
    from app.core.activity import capture_exchanges, note_exchange

    with capture_exchanges() as bucket:
        note_exchange(method="POST", url="https://hooks.slack.com/services/T000/B000/SECRETPATH", status=None, duration_ms=1,
                      error="ConnectError: for url 'https://hooks.slack.com/services/T000/B000/SECRETPATH'")
        note_exchange(method="POST", url="https://api.telegram.org/bot<redacted>/sendMessage", status=200,
                      duration_ms=1, url_is_masked=True)
    assert bucket[0]["url"] == "https://hooks.slack.com/…"
    assert "SECRETPATH" not in bucket[0]["error"] and "hooks.slack.com" in bucket[0]["error"]
    assert bucket[1]["url"] == "https://api.telegram.org/bot<redacted>/sendMessage"


async def test_old_attempt_rows_show_host_only(db_client, admin_key, db_session):
    """P03: rows stored before the change still hold the full URL; no reader gets it."""
    now = utc_now().replace(microsecond=0)
    db_session.add(DeliveryAttempt(
        channel="oldhook", kind="alert", attempt_no=1, started_at=now, duration_ms=3, outcome="failed",
        exchange=[{"method": "POST", "url": "https://discord.com/api/webhooks/1/OLDSECRET", "status": 404,
                                   "duration_ms": 3, "error": "404 for url 'https://discord.com/api/webhooks/1/OLDSECRET'"}]))
    await db_session.commit()
    h = _h(admin_key)
    read_key = (await db_client.post("/v1/api_keys", headers=h, json={"name": "viewer3", "scopes": ["read"]})).json()["key"]
    for headers in (h, _h(read_key)):
        r = await db_client.get("/v1/activity/attempts", headers=headers, params={"channel": "oldhook"})
        assert "OLDSECRET" not in r.text
        assert r.json()["items"][0]["exchange"][0]["url"] == "https://discord.com/…"


async def test_wrong_content_type_does_not_store_or_echo_the_payload(db_client, admin_key, db_session):
    """P12: FastAPI's 422 echoed the raw body as `input`; the echo was then stored."""
    h = {**_h(admin_key), "content-type": "application/x-www-form-urlencoded"}
    r = await db_client.post("/v1/channels", headers=h, content='{"name":"tg","kind":"telegram","config":{"bot_token":"BOTSECRET1"}}')
    assert r.status_code == 422 and "BOTSECRET1" not in r.text
    r = await db_client.post("/v1/auth/login", headers={"content-type": "application/x-www-form-urlencoded"},
                             content='{"username":"admin","password":"PWSECRET1"}')
    assert r.status_code == 422 and "PWSECRET1" not in r.text
    await _flush()
    rows = (await db_session.execute(select(ApiRequest))).scalars().all()
    stored = " ".join(f"{x.request_body} {x.response_body}" for x in rows)
    assert "BOTSECRET1" not in stored and "PWSECRET1" not in stored
    assert all(x.response_body is None for x in rows if x.path.startswith("/v1/auth/"))


async def test_refused_import_body_is_not_stored(db_client, admin_key, db_session):
    """P12: a refused YAML import is not JSON, so key masking never saw its secrets."""
    r = await db_client.post("/v1/config/import", headers={**_h(admin_key), "content-type": "application/yaml"},
                             content="channels:\n  - name: x\n    kind: telegram\n    config: {bot_token: YAMLSECRET1}\n  - [broken")
    await _flush()
    rows = (await db_session.execute(select(ApiRequest).where(ApiRequest.path.like("/v1/config/%")))).scalars().all()
    assert rows, r.text
    assert all(x.request_body is None for x in rows)
    assert "YAMLSECRET1" not in " ".join(str(x.response_body) for x in rows)


async def test_callers_who_did_not_get_in_leave_no_body(db_client, admin_key, db_session):
    """P08: an anonymous client must not be able to fill the table with its payloads."""
    h = _h(admin_key)
    payload = {"type": "x", "context": {"p": "A" * 3000}}
    assert (await db_client.post("/v1/fire", json=payload)).status_code == 401
    assert (await db_client.post("/v1/fire", json=payload, headers={"X-API-Key": "alertd_wrong_key_000000000000"})).status_code == 401
    assert (await db_client.post("/v1/no/such/route", json=payload)).status_code == 404
    assert (await db_client.post("/v1/inputs/999999/webhook", json=payload)).status_code in (401, 403, 404)
    inp = (await db_client.post("/v1/inputs", headers=h, json={
        "name": "locked", "kind": "webhook", "config": {"auth_required": True, "auth_token": "right-token-123456"}})).json()
    refused = await db_client.post(f"/v1/inputs/{inp['id']}/webhook", json=payload, headers={"X-Input-Token": "wrong"})
    assert refused.status_code in (401, 403)
    # A caller who did get in is still recorded with its body (an unknown type is a 4xx/202 either way).
    await db_client.post("/v1/fire", json=payload, headers=h)
    await _flush()
    rows = (await db_session.execute(select(ApiRequest).where(ApiRequest.method == "POST"))).scalars().all()
    anonymous = [x for x in rows if x.actor_name is None]
    assert len(anonymous) >= 5
    assert all(x.request_body is None for x in anonymous), [(x.path, x.status) for x in anonymous if x.request_body]
    assert any(x.request_body and "AAAA" in x.request_body for x in rows if x.path == "/v1/fire" and x.actor_name)


async def test_a_new_rule_applies_on_a_host_booted_less_than_a_ttl_ago(db_client, admin_key, monkeypatch):
    """CI on a fresh VM: monotonic() counts from boot, so with "0.0 = never
    loaded" a cache on a host up for less than the TTL looked fresh and the
    new ignore rule was not applied (the rule set loaded before it was kept)."""
    from app.core import activity_rules

    monkeypatch.setattr(activity_rules.time, "monotonic", lambda: 5.0)
    h = _h(admin_key)
    await db_client.get("/v1/templates", headers=h)          # loads the (empty) rule set
    await db_client.post("/v1/activity/rules", headers=h, json={
        "name": "boot", "match_method": "GET", "match_path": "/v1/templates*", "action": "ignore"})
    await _flush()
    before = len(await _requests(db_client, admin_key, route="/v1/templates"))
    await db_client.get("/v1/templates", headers=h)
    assert len(await _requests(db_client, admin_key, route="/v1/templates")) == before


async def test_a_load_racing_an_invalidate_is_not_kept_as_fresh():
    """A load that read the rules before a change committed must not stamp
    that old set as fresh for a whole TTL."""
    from app.core.activity_rules import RuleCache

    cache = RuleCache()
    gen = cache._generation
    cache.invalidate()                     # a rule changed while a load was running
    assert cache._generation == gen + 1
    assert cache._fresh() is False


async def test_a_failed_rule_load_is_logged_retried_soon_and_not_kept_as_fresh(db_client, monkeypatch, caplog):
    """Copilot hygiene #1: a failed load was logged at debug and the (empty)
    set stamped fresh for 60 s, so ignore rules silently did not run."""
    from app.core import activity_rules
    from app.db import session as db_session_mod

    now = [1000.0]
    monkeypatch.setattr(activity_rules.time, "monotonic", lambda: now[0])
    cache = activity_rules.RuleCache()
    real = db_session_mod.get_session_factory

    def broken():
        raise RuntimeError("database down")

    monkeypatch.setattr(db_session_mod, "get_session_factory", broken)
    with caplog.at_level("WARNING", logger="app.core.activity_rules"):
        assert await cache.rules() == []
        await cache.rules()                                  # within the retry window: no new attempt, no new line
    assert caplog.text.count("load failed") == 1
    assert cache._fresh() is True
    now[0] += activity_rules._RETRY_SEC + 0.1
    assert cache._fresh() is False, "retried after a few seconds, not a whole TTL"
    monkeypatch.setattr(db_session_mod, "get_session_factory", real)
    assert await cache.rules() == []                         # loads (no rules in this database)
    assert cache._failing is False and cache._retry_at is None
