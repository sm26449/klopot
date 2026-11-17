"""The catalog packs' rules fire on what they describe, and only on that.

Installing a pack (tests/api/test_packs_api.py) proves it is valid; this runs
each rule's expression, rendered with the pack's parameters, against
scenarios — values plus their age in the state cache — and checks exactly
which rules fire. A variable that was never received is missing (age
infinite), as on a fresh install.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from app.core.eval import evaluate, referenced_names
from app.services.packs import catalog, render


class _Snap:
    def __init__(self, age: float) -> None:
        self._age = age

    def age_sec(self) -> float:
        return self._age


class _Cache:
    def __init__(self, ages: dict[str, float]) -> None:
        self._ages = ages

    def get(self, name: str) -> _Snap | None:
        return _Snap(self._ages[name]) if name in self._ages else None


def fired(pack_id: str, values: dict[str, Any], *, ages: dict[str, float] | None = None,
          params: dict[str, Any] | None = None) -> set[str]:
    """The rules of ``pack_id`` whose condition holds. Every value is fresh
    (age 5 s) unless ``ages`` says otherwise."""
    doc = render(catalog()[pack_id], params).document
    ctx = {v["name"]: v["config"]["value"] for v in doc.get("variables", []) if v["source"] == "constant"}
    ctx.update(values)
    cache = _Cache({**{name: 5.0 for name in values}, **(ages or {})})
    out = set()
    for rule in doc.get("rules", []):
        result = evaluate(rule["condition_expr"], ctx, state_cache=cache)
        if result.ok and result.value:
            out.add(rule["name"])
    return out


@pytest.mark.parametrize("pack_id", sorted(catalog()))
def test_rules_read_only_variables_the_pack_declares(pack_id):
    doc = render(catalog()[pack_id]).document
    declared = {v["name"] for v in doc.get("variables", [])}
    for rule in doc.get("rules", []):
        # referenced_names leaves out functions and names inside strings
        # (var_age('x')), so check those quoted names separately.
        quoted = set(re.findall(r"var_age\(['\"]([^'\"]+)['\"]\)", rule["condition_expr"]))
        unknown = (referenced_names(rule["condition_expr"]) | quoted) - declared
        assert not unknown, f"{pack_id}: rule {rule['name']} reads undeclared {sorted(unknown)}"


# ── seplos-bms ────────────────────────────────────────────────────────

SEPLOS_OK = {"seplos.soc": 60, "seplos.temp_avg": 25, "seplos.cell_delta_mv": 12,
             "seplos.stale_batteries": 0, "seplos.uptime": 3600, "seplos.status": "online"}


def _seplos(**changes: Any) -> dict[str, Any]:
    return {**SEPLOS_OK, **{k.replace("__", "."): v for k, v in changes.items()}}


@pytest.mark.parametrize(("changes", "expected"), [
    ({}, set()),
    ({"seplos__soc": 18}, {"seplos_soc_low"}),
    ({"seplos__soc": 10}, {"seplos_soc_critical"}),
    ({"seplos__temp_avg": 47}, {"seplos_temp_high"}),
    ({"seplos__temp_avg": 55}, {"seplos_temp_critical"}),
    ({"seplos__cell_delta_mv": 80}, {"seplos_cell_imbalance"}),
    ({"seplos__stale_batteries": 1}, {"seplos_packs_stale"}),
    ({"seplos__status": "offline"}, {"seplos_collector_offline"}),
])
def test_seplos_each_condition_fires_its_own_alert(changes, expected):
    assert fired("seplos-bms", _seplos(**changes)) == expected


def test_seplos_a_dead_collector_raises_one_alert_not_stale_readings():
    # Readings keep their last (low) value; only the missing heartbeat speaks.
    assert fired("seplos-bms", _seplos(seplos__soc=10), ages={"seplos.uptime": 300}) == {"seplos_collector_offline"}


def test_seplos_a_steady_value_is_not_stale_while_the_heartbeat_is_fresh():
    # The collector publishes on change only: a low SoC an hour old is still low.
    assert fired("seplos-bms", _seplos(seplos__soc=18), ages={"seplos.soc": 3600}) == {"seplos_soc_low"}


def test_seplos_nothing_received_yet_is_silent():
    assert fired("seplos-bms", {}) == set()


def test_seplos_thresholds_follow_the_parameters():
    assert fired("seplos-bms", _seplos(seplos__soc=25), params={"soc_low_pct": 30}) == {"seplos_soc_low"}


# ── fronius-inverter ──────────────────────────────────────────────────

DAY = {"day_start": 0, "day_end": 24}     # in_window(0, 24): always daylight
NIGHT = {"day_start": 0, "day_end": 0}    # in_window(0, 0): never
FRONIUS_OK = {"fronius.collector": "online", "fronius.fleet": "online", "fronius.inv1.state": 4,
              "fronius.inv1.status": "online", "fronius.inv1.v_max": 236.4}


def _fronius(**changes: Any) -> dict[str, Any]:
    return {**FRONIUS_OK, **{k.replace("__", "."): v for k, v in changes.items()}}


@pytest.mark.parametrize(("changes", "expected"), [
    ({}, set()),
    ({"fronius__inv1__state": 7}, {"fronius_inv1_fault"}),
    ({"fronius__inv1__state": 5}, {"fronius_inv1_throttled"}),          # installed disabled
    ({"fronius__inv1__v_max": 254.2}, {"fronius_inv1_overvoltage"}),
    ({"fronius__inv1__v_max": 259}, {"fronius_inv1_overvoltage_critical"}),
    ({"fronius__fleet": "partial", "fronius__inv1__status": "offline"}, {"fronius_inv1_not_responding"}),
    ({"fronius__fleet": "offline", "fronius__inv1__status": "offline"}, {"fronius_fleet_offline"}),
    ({"fronius__collector": "offline"}, {"fronius_collector_offline"}),
])
def test_fronius_each_condition_fires_its_own_alert(changes, expected):
    assert fired("fronius-inverter", _fronius(**changes), params=DAY) == expected


def test_fronius_mppt_is_normal_production_not_throttling():
    # SunSpec 4 is MPPT; our first configuration took it for "throttled".
    assert fired("fronius-inverter", _fronius(fronius__inv1__state=4), params=DAY) == set()


def test_fronius_inverters_asleep_at_night_are_not_an_outage():
    night = _fronius(fronius__fleet="offline", fronius__inv1__status="offline")
    assert fired("fronius-inverter", night, params=NIGHT) == set()


def test_fronius_state_7_after_dark_is_not_a_fault():
    # Seen on a real site: idle Fronius inverters report SunSpec 7 at night.
    assert fired("fronius-inverter", _fronius(fronius__inv1__state=7), params=NIGHT) == set()


def test_fronius_a_dead_collector_raises_one_alert_not_stale_readings():
    stale = _fronius(fronius__inv1__state=7, fronius__inv1__v_max=259)
    assert fired("fronius-inverter", stale, ages={"fronius.fleet": 600}, params=DAY) == {"fronius_collector_offline"}


def test_fronius_names_follow_the_inverter_id():
    values = {k.replace("inv1", "inv3"): v for k, v in _fronius(fronius__inv1__state=7).items()}
    assert fired("fronius-inverter", values, params={**DAY, "inverter_id": 3}) == {"fronius_inv3_fault"}


# ── the API-only packs: every template OpenVigil / MBG fires is there ──

def test_openvigil_has_a_template_for_every_type_it_sends():
    sent = {"nvr_cadere", "nvr_camera_cazuta", "nvr_nvr_cazut", "nvr_disc_plin", "nvr_fluxuri_lipsa",
            "nvr_flux_regenerat", "nvr_zgomot", "nvr_regula", "nvr_intrus", "nvr_intrus_acasa",
            "nvr_inregistrare_bucla", "nvr_curatare_esuata", "nvr_spatiu_insuficient",
            "nvr_inregistrare_problema", "nvr_inregistrare_oprita", "nvr_backup_esuat", "nvr_rezumat"}
    recovered = {"nvr_camera_revenita", "nvr_nvr_revenit", "nvr_disc_ok", "nvr_inregistrare_reluata"}
    types = {t["type"] for t in render(catalog()["openvigil-nvr"]).document["templates"]}
    assert types == sent | recovered


def test_mbg_matches_the_gateways_own_catalog():
    # multibus/outputs/alerting/alertd_catalog.py: 12 event types, 6 resolutions
    # (MBG ADR-0053 paired episodes), 3 conditions.
    paired = {"mbg_device", "mbg_sink", "mbg_device_alarm", "mbg_bridge", "mbg_vmeter", "mbg_rules_engine"}
    resolutions = {f"{t}_ok" for t in paired}
    expected = paired | resolutions | {
        "mbg_influx_auth", "mbg_influx_dropped", "mbg_config", "mbg_gateway", "mbg_event", "mbg_test",
        "mbg_latency", "mbg_influx_buffer", "mbg_threshold"}
    doc = render(catalog()["multi-bus-gateway"]).document
    templates = {t["type"]: t for t in doc["templates"]}
    assert set(templates) == expected
    assert {r["template"] for r in doc["routes"]} == expected
    # No per-type cooldown on either side of a pair: it would swallow a second
    # device's failure, or a recovery notice.
    assert all(templates[t]["min_repeat_min"] == 0 for t in paired | resolutions)
    assert all(templates[t]["severity"] == "info" for t in resolutions)
