"""Every script talks to THIS install's port (review K18).

The pre-release audit fix made bootstrap.sh read ``KLOPOT_HTTP_PORT`` from ``.env``; deploy.sh
and restore_drill.sh still probed a fixed 5090 — on a custom port a foreign
service's 200 made a failed deploy look healthy. All three now use one helper.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "scripts" / "_klopot_url.sh"


def _url(cwd: Path, env: dict[str, str] | None = None) -> str:
    out = subprocess.run(["bash", "-c", f'. "{HELPER}"; klopot_url'], cwd=cwd, env=env or {"PATH": "/usr/bin:/bin"},
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.mark.parametrize(("line", "url"), [
    ("KLOPOT_HTTP_PORT=5191", "http://127.0.0.1:5191"),
    ('KLOPOT_HTTP_PORT="5192"', "http://127.0.0.1:5192"),
    ("OTHER=1", "http://127.0.0.1:5090"),
])
def test_the_port_comes_from_env(tmp_path, line, url):
    (tmp_path / ".env").write_text(f"{line}\n")
    assert _url(tmp_path) == url


def test_alertd_url_wins(tmp_path):
    (tmp_path / ".env").write_text("KLOPOT_HTTP_PORT=5191\n")
    assert _url(tmp_path, {"PATH": "/usr/bin:/bin", "ALERTD_URL": "http://h:1"}) == "http://h:1"


@pytest.mark.parametrize("script", ["bootstrap.sh", "deploy.sh", "restore_drill.sh"])
def test_no_script_hardcodes_the_port(script):
    text = (ROOT / "scripts" / script).read_text()
    assert "_klopot_url.sh" in text
    assert ":5090}" not in text
