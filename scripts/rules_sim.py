"""Rule engine end to end over a real MQTT broker — driven by scripts/rules_sim.sh.

Imports one config (an MQTT input, variables of every kind, templates, rules)
into a throwaway Klopot, then runs every scenario in lock-step phases: each
phase publishes its MQTT messages, waits, and checks what the engine did —
through the public API only (rules, log, incidents). A scenario covers one
behaviour: thresholds and persistence, strings, JSON paths, regexes, literals,
missing / stale / null inputs, computed and aggregate variables, hysteresis
incidents, inhibition, auto-disable, template rendering, the stage-2
functions (fresh / has / coalesce / between / any / all, minutes in
in_window, the sun), and the write-time checks (a regex RE2 cannot run and an
unknown function are refused).

Environment (set by rules_sim.sh): SIM_URL, SIM_ADMIN_KEY, SIM_MQTT_PORT,
SIM_BROKER_HOST; SIM_ONLY=<substring> runs only matching scenarios.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import paho.mqtt.client as mqtt

URL = os.environ["SIM_URL"]
KEY = os.environ["SIM_ADMIN_KEY"]
MQTT_PORT = int(os.environ["SIM_MQTT_PORT"])
BROKER_HOST = os.environ["SIM_BROKER_HOST"]
ONLY = os.environ.get("SIM_ONLY", "")
PHASE_SEC = float(os.environ.get("SIM_PHASE_SEC", "6"))

api = httpx.Client(base_url=URL, headers={"X-API-Key": KEY}, timeout=20)


# ── Building blocks ────────────────────────────────────────────────

Pub = tuple[str, Any, float]          # topic, payload, seconds to wait after it


@dataclass
class Phase:
    publish: list[Pub] = field(default_factory=list)
    check: Callable[[Sim], None] | None = None


@dataclass
class Scenario:
    name: str
    what: str
    variables: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    templates: list[dict[str, Any]] = field(default_factory=list)


class CheckFailed(AssertionError):
    pass


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise CheckFailed(msg)


def mvar(name: str, topic: str, type_: str = "number", stale: int = 600, **extra: Any) -> dict[str, Any]:
    return {"name": name, "source": "mqtt", "input": "sim_mqtt",
            "config": {"topic": topic, "type": type_, "stale_after_sec": stale, **extra}}


def rule(name: str, cond: str, *, persist: int = 1, template: str = "sim_alert", **extra: Any) -> dict[str, Any]:
    return {"name": name, "template_type": template, "condition_expr": cond,
            "persist_n": persist, "eval_interval_sec": 1, **extra}


class Sim:
    """API reads used by the checks, with per-phase memory of fire counts."""

    def __init__(self) -> None:
        self.marks: dict[str, int] = {}

    def rule(self, name: str) -> dict[str, Any]:
        r = api.get(f"/v1/rules/by-name/{name}")
        r.raise_for_status()
        return r.json()

    def fires(self, name: str) -> int:
        """Notifications the rule delivered so far."""
        return int(self.rule(name)["fire_count_lifetime"])

    def mark(self, name: str) -> None:
        self.marks[name] = self.fires(name)

    def new_fires(self, name: str) -> int:
        return self.fires(name) - self.marks.get(name, 0)

    def log(self, name: str) -> list[dict[str, Any]]:
        rid = self.rule(name)["id"]
        r = api.get("/v1/log", params={"rule_id": rid, "limit": 500})
        r.raise_for_status()
        return r.json()["items"]

    def incidents(self, name: str) -> list[dict[str, Any]]:
        rid = self.rule(name)["id"]
        r = api.get("/v1/incidents", params={"rule_id": rid})
        r.raise_for_status()
        return r.json()["items"]


def fired(name: str) -> Callable[[Sim], None]:
    def check(s: Sim) -> None:
        expect(s.new_fires(name) > 0, f"{name}: expected a fire, got none ({s.rule(name)['last_eval_error']})")
        s.mark(name)
    return check


def silent(name: str, status: str | None = None) -> Callable[[Sim], None]:
    def check(s: Sim) -> None:
        r = s.rule(name)
        expect(s.new_fires(name) == 0, f"{name}: expected no fire, got {s.new_fires(name)}")
        if status:
            expect(r["eval_status"] == status, f"{name}: eval_status {r['eval_status']!r}, expected {status!r} ({r['last_eval_error']})")
        s.mark(name)
    return check


def both(*checks: Callable[[Sim], None]) -> Callable[[Sim], None]:
    def check(s: Sim) -> None:
        for c in checks:
            c(s)
    return check


# ── Scenarios ──────────────────────────────────────────────────────

SCENARIOS: list[Scenario] = [
    Scenario(
        "threshold", "number above a threshold, persist_n=2",
        [mvar("sim.temp", "sim/temp")],
        [rule("sim_threshold", "sim.temp > 50", persist=2)],
        [Phase([("sim/temp", 40, 0)], silent("sim_threshold", "ok")),
         Phase([("sim/temp", 60, 0)], fired("sim_threshold")),
         Phase([("sim/temp", 45, 0)], both(lambda s: time.sleep(1.5), lambda s: s.mark("sim_threshold"))),
         Phase([], silent("sim_threshold", "ok"))],
    ),
    Scenario(
        "persist_flap", "a value that flips every second never reaches persist_n=4",
        [mvar("sim.flap", "sim/flap")],
        [rule("sim_persist_flap", "sim.flap > 50", persist=4)],
        [Phase([("sim/flap", v, 1.0) for v in (60, 10, 60, 10, 60)] + [("sim/flap", 10, 0)], silent("sim_persist_flap", "ok")),
         Phase([("sim/flap", 60, 0)], fired("sim_persist_flap"))],
    ),
    Scenario(
        "string_in", "string membership with `in [...]` and lower()",
        [mvar("sim.state", "sim/state", "string")],
        [rule("sim_string_in", 'lower(sim.state) in ["fault", "alarm"]')],
        [Phase([("sim/state", "running", 0)], silent("sim_string_in", "ok")),
         Phase([("sim/state", "FAULT", 0)], fired("sim_string_in"))],
    ),
    Scenario(
        "json_path", "a value taken from a JSON payload by json_path",
        [mvar("sim.jp", "sim/json", "number", json_path="data.level")],
        [rule("sim_json_path", "sim.jp >= 7")],
        [Phase([("sim/json", {"data": {"level": 3}}, 0)], silent("sim_json_path", "ok")),
         Phase([("sim/json", {"data": {"level": 9}}, 0)], fired("sim_json_path"))],
    ),
    Scenario(
        "regex_contains", "regex_match (RE2) and contains on a peer list",
        [mvar("sim.peers", "sim/peers", "string")],
        [rule("sim_regex_contains",
              'regex_match(sim.peers, "[0-9]") AND NOT regex_match(sim.peers, "^10[.]0[.]0[.](1|2)(,10[.]0[.]0[.](1|2))*$") '
              'AND NOT contains(sim.peers, "ignore")')],
        [Phase([("sim/peers", "10.0.0.1,10.0.0.2", 0)], silent("sim_regex_contains", "ok")),
         Phase([("sim/peers", "10.0.0.1,10.0.0.9", 0)], fired("sim_regex_contains"))],
    ),
    Scenario(
        "bool_literal", "bool variable against the lowercase literal `true` (RL-08)",
        [mvar("sim.flag", "sim/flag", "bool")],
        [rule("sim_bool_literal", "sim.flag == true")],
        [Phase([("sim/flag", "false", 0)], silent("sim_bool_literal", "ok")),
         Phase([("sim/flag", "true", 0)], fired("sim_bool_literal"))],
    ),
    Scenario(
        "vars_extract_forgot", "vars_extract lists another variable; the one the condition reads is still seen (RL-03)",
        [mvar("sim.forgot", "sim/forgot"), mvar("sim.listed", "sim/listed")],
        [rule("sim_vars_extract_forgot", "sim.forgot > 5", vars_extract=["sim.listed"])],
        [Phase([("sim/listed", 1, 0), ("sim/forgot", 1, 0)], silent("sim_vars_extract_forgot", "ok")),
         Phase([("sim/forgot", 9, 0)], fired("sim_vars_extract_forgot"))],
    ),
    Scenario(
        "undotted_missing", "an undotted variable with no value is no_data, not an error (RL-05)",
        [mvar("simple_level", "sim/simple")],
        [rule("sim_undotted_missing", "simple_level > 5")],
        [Phase([], silent("sim_undotted_missing", "no_data")),
         Phase([("sim/simple", 8, 0)], fired("sim_undotted_missing"))],
    ),
    Scenario(
        "null_value", "a JSON null is no_data, not an error (RL-06)",
        [mvar("sim.nul", "sim/nul", "json")],
        [rule("sim_null_value", "sim.nul > 5")],
        [Phase([("sim/nul", None, 0)], silent("sim_null_value", "no_data")),
         Phase([("sim/nul", 9, 0)], fired("sim_null_value"))],
    ),
    Scenario(
        "avg_missing", "avg() over inputs that never arrived waits for data instead of reading 0 (RL-07)",
        [mvar("sim.a1", "sim/a1"), mvar("sim.a2", "sim/a2")],
        [rule("sim_avg_missing", "avg([sim.a1, sim.a2]) < 5")],
        [Phase([], silent("sim_avg_missing", "no_data")),
         Phase([("sim/a1", 2, 0), ("sim/a2", 4, 0)], fired("sim_avg_missing"))],
    ),
    Scenario(
        "stale", "a value older than stale_after_sec leaves the context: the rule stops firing, no_data",
        [mvar("sim.st", "sim/stale", stale=3)],
        [rule("sim_stale", "sim.st > 5")],
        [Phase([("sim/stale", 9, 0)], fired("sim_stale")),
         Phase([], both(lambda s: time.sleep(1), lambda s: s.mark("sim_stale"))),
         Phase([], silent("sim_stale", "no_data"))],
    ),
    Scenario(
        "heartbeat", "var_age() guard: a heartbeat that stops publishing fires",
        [mvar("sim.hb", "sim/hb")],
        [rule("sim_heartbeat", 'var_age("sim.hb") > 8 AND var_age("sim.hb") < 600')],
        [Phase([("sim/hb", 1, 1.0), ("sim/hb", 1, 1.0), ("sim/hb", 1, 1.0), ("sim/hb", 1, 0)], silent("sim_heartbeat", "ok")),
         Phase([], fired("sim_heartbeat"))],
    ),
    Scenario(
        "computed", "computed variable (formula over two MQTT values)",
        [mvar("sim.c1", "sim/c1"), mvar("sim.c2", "sim/c2"),
         {"name": "sim.csum", "source": "computed", "config": {"formula": "sim.c1 + sim.c2"}}],
        [rule("sim_computed", "sim.csum > 10")],
        [Phase([("sim/c1", 2, 0), ("sim/c2", 3, 0)], silent("sim_computed", "ok")),
         Phase([("sim/c2", 9, 0)], fired("sim_computed"))],
    ),
    Scenario(
        "aggregate", "aggregate variable (sum over two topics)",
        [{"name": "sim.agg", "source": "aggregate", "input": "sim_mqtt",
          "config": {"topics": ["sim/agg/a", "sim/agg/b"], "aggregate": "sum", "stale_after_sec": 600}}],
        [rule("sim_aggregate", "sim.agg >= 100")],
        [Phase([("sim/agg/a", 30, 0), ("sim/agg/b", 30, 0)], silent("sim_aggregate", "ok")),
         Phase([("sim/agg/b", 80, 0)], fired("sim_aggregate"))],
    ),
    Scenario(
        "time_window", "time helpers that are always true (in_window over the whole day, hours and HH:MM, month, weekend)",
        [mvar("sim.tw", "sim/tw")],
        [rule("sim_time_window", 'in_window(0, 24) AND in_window("00:00", "24:00") AND dow_now() >= 0 AND hour_now() < 24 '
              "AND month_now() >= 1 AND (is_weekend() OR NOT is_weekend()) AND sim.tw == 1")],
        [Phase([("sim/tw", 1, 0)], fired("sim_time_window"))],
    ),
    Scenario(
        "sun", "sun_elevation() / is_daylight() with ALERTD_LATITUDE / ALERTD_LONGITUDE set (RL-25)",
        [mvar("sim.sun", "sim/sun")],
        [rule("sim_sun", "sun_elevation() > -90 AND (is_daylight() OR NOT is_daylight()) AND sim.sun == 1")],
        [Phase([("sim/sun", 0, 0)], silent("sim_sun", "ok")),
         Phase([("sim/sun", 1, 0)], fired("sim_sun"))],
    ),
    Scenario(
        "fresh_has", "fresh() / has(): fires on new data, goes quiet (status ok) once it is older than 4 s (RL-20, RL-21)",
        [mvar("sim.fr", "sim/fr")],
        [rule("sim_fresh_has", 'fresh("sim.fr", 4) AND has("sim.fr") AND sim.fr > 5')],
        [Phase([], silent("sim_fresh_has", "ok")),
         Phase([("sim/fr", 9, 0)], fired("sim_fresh_has")),
         Phase([], both(lambda s: time.sleep(1), lambda s: s.mark("sim_fresh_has"))),
         Phase([], silent("sim_fresh_has", "ok"))],
    ),
    Scenario(
        "coalesce_between", "coalesce() gives a missing input a default (status ok, not no_data); between() (RL-21, RL-22)",
        [mvar("sim.cb", "sim/cb")],
        [rule("sim_coalesce_between", "between(coalesce(sim.cb, 50), 10, 20)")],
        [Phase([], silent("sim_coalesce_between", "ok")),
         Phase([("sim/cb", 25, 0)], silent("sim_coalesce_between", "ok")),
         Phase([("sim/cb", 15, 0)], fired("sim_coalesce_between"))],
    ),
    Scenario(
        "any_all", "any() / all() over a list instead of OR / AND chains (RL-23)",
        [mvar("sim.s1", "sim/s1"), mvar("sim.s2", "sim/s2"), mvar("sim.s3", "sim/s3")],
        [rule("sim_any_all", "any([sim.s1 == 7, sim.s2 == 7, sim.s3 == 7]) AND all([sim.s1 > 0, sim.s2 > 0, sim.s3 > 0])")],
        [Phase([("sim/s1", 1, 0), ("sim/s2", 1, 0), ("sim/s3", 1, 0)], silent("sim_any_all", "ok")),
         Phase([("sim/s2", 7, 0)], fired("sim_any_all"))],
    ),
    Scenario(
        "render", "the template renders the rule's values into the title",
        [mvar("sim.rv", "sim/rv")],
        [rule("sim_render", "sim.rv > 0", template="sim_render")],
        [Phase([("sim/rv", 42.5, 0)], lambda s: expect(
            any("42.5" in (e.get("title") or "") for e in s.log("sim_render")),
            f"sim_render: no log title with the value: {[e.get('title') for e in s.log('sim_render')][:3]}"))],
        templates=[{"type": "sim_render", "severity": "warning", "title_template": "Render check: value {sim.rv | fixed(1)}",
                    "message_template": "v={sim.rv}", "min_repeat_min": 0}],
    ),
    Scenario(
        "incident", "incident with hysteresis: opens above 80, stays open at 78, resolves below 75 (2 confirmations)",
        [mvar("sim.inc", "sim/inc")],
        [rule("sim_incident", "sim.inc > 80", incident_enabled=True, recovery_expr="sim.inc < 75",
              recovery_persist_n=2, resolved_template_type="sim_resolved")],
        [Phase([("sim/inc", 90, 0)], lambda s: expect(
            [i["state"] for i in s.incidents("sim_incident")] == ["active"], f"sim_incident: {s.incidents('sim_incident')}")),
         Phase([("sim/inc", 78, 0)], lambda s: expect(
             [i["state"] for i in s.incidents("sim_incident")] == ["active"], "sim_incident: closed inside the hysteresis band")),
         Phase([("sim/inc", 70, 0)], lambda s: expect(
             [i["state"] for i in s.incidents("sim_incident")] == ["resolved"], f"sim_incident: {s.incidents('sim_incident')}"))],
        templates=[{"type": "sim_resolved", "severity": "info", "title_template": "Recovered: {sim.inc}", "message_template": "sim", "min_repeat_min": 0}],
    ),
    Scenario(
        "inhibition", "a rule inhibited by an active root-cause rule is suppressed as `inhibited`",
        [mvar("sim.root", "sim/root"), mvar("sim.leaf", "sim/leaf")],
        [rule("sim_root_cause", "sim.root == 1"),
         rule("sim_inhibited", "sim.leaf == 1", template="sim_leaf", inhibited_by=["sim_root_cause"])],
        [Phase([("sim/root", 1, 0.5), ("sim/leaf", 1, 0)], lambda s: (
            expect(s.new_fires("sim_inhibited") == 0, "sim_inhibited delivered while its inhibitor was active"),
            expect(any(e.get("suppressed_reason") == "inhibited" for e in s.log("sim_inhibited")),
                   "sim_inhibited: no log row suppressed as inhibited"),
            s.mark("sim_inhibited"))),
         Phase([("sim/root", 0, 0)], fired("sim_inhibited"))],
        templates=[{"type": "sim_leaf", "severity": "warning", "title_template": "Leaf {sim.leaf}", "message_template": "sim", "min_repeat_min": 0}],
    ),
    Scenario(
        "auto_disable", "a rule that keeps failing is auto-disabled (threshold 5 in this stack) and announced",
        [mvar("sim.ad", "sim/ad")],
        [rule("sim_auto_disable", "sim.ad / 0 > 1")],
        [Phase([("sim/ad", 1, 0)], lambda s: time.sleep(1)),
         Phase([], lambda s: (
             expect(s.rule("sim_auto_disable")["enabled"] is False, "sim_auto_disable still enabled"),
             expect(api.get("/v1/log", params={"type": "rule_auto_disabled"}).json()["total"] >= 1,
                    "no rule_auto_disabled notification")))],
    ),
]


def write_time_checks() -> None:
    """RL-01 / RL-26: a regex RE2 cannot run and an unknown function are
    refused when the rule is saved."""
    r = api.post("/v1/rules", json={"name": "sim_lookahead", "template_type": "sim_alert",
                                    "condition_expr": 'regex_match(sim.peers, "x(?!y)")'})
    expect(r.status_code == 422 and "lookahead" in r.text, f"lookahead rule not refused: {r.status_code} {r.text[:200]}")
    r = api.post("/v1/rules", json={"name": "sim_typo", "template_type": "sim_alert",
                                    "condition_expr": 'fersh("sim.fr", 4)'})
    expect(r.status_code == 422 and "unknown function" in r.text, f"unknown function not refused: {r.status_code} {r.text[:200]}")
    v = api.post("/v1/rules/validate", json={"condition_expr": "contains(sim.peers, 'STATUS') and sim.temp > 1"}).json()
    expect("STATUS" not in v["unknown_vars"], f"validate reports string contents as variables: {v['unknown_vars']}")


# ── Runner ─────────────────────────────────────────────────────────

def config(scenarios: list[Scenario]) -> dict[str, Any]:
    templates = [{"type": "sim_alert", "severity": "warning", "title_template": "Sim alert", "message_template": "sim", "min_repeat_min": 0}]
    for s in scenarios:
        templates += s.templates
    return {
        "version": "1.0",
        "inputs": [{"name": "sim_mqtt", "kind": "mqtt", "config": {"host": BROKER_HOST, "port": 1883}}],
        # Its own UI channel: ui_default's 30/min rate limit (rightly) defers a
        # burst of this size, which would read as "the rule did not fire".
        "channels": [{"name": "sim_ui", "kind": "ui", "config": {}, "rate_limit_per_min": 10000}],
        "templates": templates,
        "routes": [{"template": t["type"], "channel": "sim_ui", "severity_min": "info"} for t in templates],
        "variables": [v for s in scenarios for v in s.variables],
        "rules": [r for s in scenarios for r in s.rules],
    }


def publish_all(client: mqtt.Client, pubs: list[Pub]) -> None:
    for topic, payload, wait in pubs:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        client.publish(topic, body, qos=1).wait_for_publish(5)
        if wait:
            time.sleep(wait)


def main() -> int:
    scenarios = [s for s in SCENARIOS if ONLY in s.name]
    n_rules = sum(len(s.rules) for s in scenarios)
    n_msgs = sum(len(p.publish) for s in scenarios for p in s.phases)
    print(f"== {len(scenarios)} scenarios, {n_rules} rules, {n_msgs} MQTT messages")

    r = api.post("/v1/config/import", params={"apply": "true"}, content=json.dumps(config(scenarios)),
                 headers={"Content-Type": "application/yaml"})
    r.raise_for_status()
    body = r.json()
    if not body.get("applied"):
        print("import failed:", json.dumps(body, indent=1)[:2000])
        return 1

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"rulesim-{os.getpid()}")
    client.connect("127.0.0.1", MQTT_PORT)
    client.loop_start()
    time.sleep(3)                       # the app's MQTT input subscribes after the import reload

    sim = Sim()
    failures: dict[str, str] = {}
    try:
        write_time_checks()
        print("  ok   write-time checks (lookahead and unknown function refused, validate ignores string contents)")
    except CheckFailed as e:
        failures["write_time"] = str(e)
        print(f"  FAIL write-time checks: {e}")

    for s in scenarios:
        for rl in s.rules:
            sim.mark(rl["name"])
    for i in range(max(len(s.phases) for s in scenarios)):
        active = [s for s in scenarios if i < len(s.phases) and s.name not in failures]
        threads = [threading.Thread(target=publish_all, args=(client, s.phases[i].publish)) for s in active]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        time.sleep(PHASE_SEC)
        for s in active:
            check = s.phases[i].check
            if check is None:
                continue
            try:
                check(sim)
            except CheckFailed as e:
                failures[s.name] = f"phase {i + 1}: {e}"

    for s in scenarios:
        status = "FAIL" if s.name in failures else "ok  "
        print(f"  {status} {s.name:<22} {s.what}")
        if s.name in failures:
            print(f"         → {failures[s.name]}")
    client.loop_stop()
    client.disconnect()
    total = len(scenarios) + 1
    print(f"== {total - len(failures)}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
