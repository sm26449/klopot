#!/usr/bin/env python3
"""Klopot's version, in every file that carries it — one command to read,
check and change it (docs/RELEASING.md).

    scripts/version.py                  # the version, e.g. 1.3.0-rc.1
    scripts/version.py tag              # its git tag, v1.3.0-rc.1
    scripts/version.py check            # every file agrees (exit 1 if not)
    scripts/version.py prerelease       # exit 0 for a release candidate, 1 for a final
    scripts/version.py set 1.3.0-rc.1   # write it everywhere

A version is ``X.Y.Z`` (a final) or ``X.Y.Z-rc.N`` (a release candidate) —
SemVer, the form of the git tag, the image tag, the API (``/v1/version``),
the admin UI and the TypeScript SDK. The Python packaging files take the
same version in PEP 440 form (``1.3.0rc1``), which is what pip shows.

After ``set``: ``scripts/dump_openapi.py`` and ``scripts/generate_sdks.sh``
(the version is in the OpenAPI document and the SDKs), then the release
commit. Standard library only: CI runs it before installing anything.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-rc\.([1-9]\d*))?$")


def pep440(version: str) -> str:
    """``1.3.0-rc.1`` → ``1.3.0rc1``; a final is unchanged."""
    m = VERSION_RE.match(version)
    if not m:
        raise ValueError(f"not a Klopot version (X.Y.Z or X.Y.Z-rc.N): {version!r}")
    major, minor, patch, rc = m.groups()
    return f"{major}.{minor}.{patch}" + (f"rc{rc}" if rc else "")


def is_prerelease(version: str) -> bool:
    return pep440(version) != version


@dataclass(frozen=True)
class Spot:
    """One place a version is written: a file, the line's pattern (group 1 =
    the text before the version, group 2 = the version), and its form."""
    path: str
    pattern: str
    form: str  # "semver" | "pep440"

    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.MULTILINE)


SPOTS = (
    Spot("app/__init__.py", r'^(__version__ = ")([^"]+)"', "semver"),
    Spot("sdk/typescript/package.json", r'^(  "version": ")([^"]+)"', "semver"),
    Spot("pyproject.toml", r'^(version = ")([^"]+)"', "pep440"),
    Spot("sdk/python/pyproject.toml", r'^(version = ")([^"]+)"', "pep440"),
    Spot("sdk/python-client.yaml", r'^(package_version_override: ")([^"]+)"', "pep440"),
)


def _read(root: Path, spot: Spot) -> str:
    m = spot.regex().search((root / spot.path).read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"{spot.path}: no version line matching {spot.pattern}")
    return m.group(2)


def current(root: Path = ROOT) -> str:
    """The version, from ``app/__init__.py``."""
    return _read(root, SPOTS[0])


def mismatches(root: Path = ROOT) -> list[str]:
    """Every file whose version is not the one ``app/__init__.py`` names."""
    version = current(root)
    want = {"semver": version, "pep440": pep440(version)}
    return [f"{s.path}: {found!r}, expected {want[s.form]!r}"
            for s in SPOTS if (found := _read(root, s)) != want[s.form]]


def write(version: str, root: Path = ROOT) -> None:
    forms = {"semver": version, "pep440": pep440(version)}   # validates first
    for spot in SPOTS:
        path = root / spot.path
        text, n = spot.regex().subn(lambda m, s=spot: f'{m.group(1)}{forms[s.form]}"',
                                    path.read_text(encoding="utf-8"), count=1)
        if n != 1:
            raise SystemExit(f"{spot.path}: no version line matching {spot.pattern}")
        path.write_text(text, encoding="utf-8")


def main(argv: list[str]) -> int:
    cmd, *rest = argv or ["show"]
    if cmd == "show":
        print(current())
    elif cmd == "tag":
        print(f"v{current()}")
    elif cmd == "check":
        bad = mismatches()
        for line in bad:
            print(f"version mismatch — {line}", file=sys.stderr)
        return 1 if bad else 0
    elif cmd == "prerelease":
        return 0 if is_prerelease(current()) else 1
    elif cmd == "set" and len(rest) == 1:
        try:
            write(rest[0])
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        print(f"{rest[0]} written; now scripts/dump_openapi.py and scripts/generate_sdks.sh")
    else:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
