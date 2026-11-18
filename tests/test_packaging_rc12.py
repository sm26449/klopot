"""rc.9 review RC-11 / RC-12: what goes into the wheel and the build context."""
from __future__ import annotations

import tomllib
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_wheel_carries_every_pack():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]["app"]
    packs = [p.relative_to(ROOT / "app").as_posix() for p in (ROOT / "app" / "packs").glob("*.yaml")]
    assert packs, "no packs found"
    missing = [p for p in packs if not any(fnmatch(p, pattern) for pattern in data)]
    assert not missing, f"add to [tool.setuptools.package-data]: {missing}"


def test_local_only_directories_stay_out_of_the_build_context():
    ignored = {line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines()}
    for path in ("private/", ".audit/", "node_modules/", ".env", "secrets.env", "backups/"):
        assert path in ignored, f"{path} must be in .dockerignore"
