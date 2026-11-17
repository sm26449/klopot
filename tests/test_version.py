"""scripts/version.py — one version in every file that carries it, and the
release-candidate form (docs/RELEASING.md)."""
from __future__ import annotations

import shutil

import pytest

from app import __version__
from scripts import version


def test_every_file_carries_the_same_version():
    assert version.mismatches() == []
    assert version.current() == __version__


@pytest.mark.parametrize(("semver", "pep440", "pre"), [
    ("1.3.0", "1.3.0", False), ("1.3.0-rc.1", "1.3.0rc1", True), ("2.10.4-rc.12", "2.10.4rc12", True),
])
def test_forms(semver, pep440, pre):
    assert version.pep440(semver) == pep440
    assert version.is_prerelease(semver) is pre


@pytest.mark.parametrize("bad", ["1.3", "v1.3.0", "1.3.0rc1", "1.3.0-rc1", "1.3.0-rc.0", "1.3.0-beta.1", "1.3.0-rc.1 "])
def test_only_finals_and_numbered_release_candidates(bad):
    with pytest.raises(ValueError, match="not a Klopot version"):
        version.pep440(bad)


def test_set_writes_every_file_in_its_form(tmp_path):
    for spot in version.SPOTS:
        (tmp_path / spot.path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(version.ROOT / spot.path, tmp_path / spot.path)
    version.write("9.8.7-rc.2", tmp_path)
    assert version.current(tmp_path) == "9.8.7-rc.2"
    assert version.mismatches(tmp_path) == []
    assert 'version = "9.8.7rc2"' in (tmp_path / "pyproject.toml").read_text()
    assert '"version": "9.8.7-rc.2"' in (tmp_path / "sdk/typescript/package.json").read_text()
    with pytest.raises(ValueError, match="not a Klopot version"):
        version.write("9.8.7-beta", tmp_path)
    assert version.current(tmp_path) == "9.8.7-rc.2", "a refused version changes nothing"
