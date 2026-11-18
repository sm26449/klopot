"""deploy.sh warns when a runtime dir's compose configuration does not pass a
setting the checkout passes (2026-11-18: the runtime's old docker-compose.yml
dropped ALERTD_LATITUDE and four older settings without a word)."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "scripts" / "_compose_drift.sh"
CHECKOUT = ROOT / "docker-compose.yml"


def _missing(config: str) -> list[str]:
    out = subprocess.run(["bash", "-c", f'. "{HELPER}"; compose_missing_settings "{CHECKOUT}"'],
                         input=config, capture_output=True, text=True, check=True)
    return out.stdout.split()


def test_an_up_to_date_configuration_misses_nothing():
    assert _missing(CHECKOUT.read_text()) == []


def test_settings_dropped_by_an_old_copy_are_named():
    old = "\n".join(line for line in CHECKOUT.read_text().splitlines()
                    if "ALERTD_LATITUDE" not in line and "ALERTD_ADMIN_ALLOW_CIDRS" not in line)
    assert _missing(old) == ["ALERTD_ADMIN_ALLOW_CIDRS", "ALERTD_LATITUDE"]


def test_no_configuration_says_nothing():
    """`docker compose config` failed: no false alarm."""
    assert _missing("") == []


def test_deploy_runs_the_check_in_its_preflight():
    text = (ROOT / "scripts" / "deploy.sh").read_text()
    assert '. "$SRC/scripts/_compose_drift.sh"' in text
    assert "compose_missing_settings" in text
