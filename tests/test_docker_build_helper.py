"""scripts/_docker_build.sh: a build that fails with the broken-BuildKit
signature says so and names the remedy; any other failure does not; the
build's status always comes through. No Docker: the "build" is a stub."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parent.parent / "scripts" / "_docker_build.sh"


def _run(stub: str, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    env = "BUILD_QUIET=1 " if quiet else ""
    script = f'. "{HELPER}"; fake() {{ {stub}; }}; {env}build_or_explain fake'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("line", [
    'ERROR: failed to solve: lease "1p99lew6r7d76megkl4w14d83": not found',
    "ERROR: failed to read dockerfile: failed to walk: resolve : lstat "
    "/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/53430: no such file or directory",
])
def test_the_buildkit_signature_names_the_remedy(line):
    done = _run(f"echo '{line}' >&2; return 1")
    assert done.returncode == 1
    assert "docker builder prune -a" in done.stderr


def test_another_failure_is_passed_through_without_the_hint():
    done = _run("echo 'COPY failed: file not found' >&2; return 7")
    assert done.returncode == 7
    assert "COPY failed" in done.stderr
    assert "prune" not in done.stderr


def test_success_prints_the_tail_unless_quiet():
    assert "naming to klopot:x" in _run("echo 'naming to klopot:x'").stdout
    quiet = _run("echo 'naming to klopot:x'", quiet=True)
    assert quiet.returncode == 0
    assert quiet.stdout == ""
