"""scripts/backup.sh never passes a failed dump off as a backup (audit P09).

The script piped ``mysqldump | gzip``: the pipeline's status was gzip's, so a
dump that failed left a 20-byte ``.sql.gz``, logged "backup done" and exited
0, while rotation kept deleting the good backups. These tests run the real
script with a stand-in ``mysqldump`` on PATH.
"""
from __future__ import annotations

import gzip
import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup.sh"

GOOD = """#!/bin/sh
echo "-- MySQL dump"
echo "CREATE TABLE t (id INT);"
echo "-- Dump completed on 2026-11-15  2:00:11"
"""
FAILS = """#!/bin/sh
echo "-- MySQL dump"
echo "mysqldump: Got error: 2002: Can't connect to MySQL server" >&2
exit 2
"""
# Exit 0 but cut short: e.g. killed after the header, or a full disk.
TRUNCATED = """#!/bin/sh
echo "-- MySQL dump"
echo "CREATE TABLE t (id INT);"
"""


def _run(tmp_path: Path, mysqldump: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    bindir, backups = tmp_path / "bin", tmp_path / "backups"
    bindir.mkdir()
    stub = bindir / "mysqldump"
    stub.write_text(mysqldump)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {
        "PATH": f"{bindir}:{os.environ['PATH']}", "BACKUP_DIR": str(backups),
        "MYSQL_HOST": "db", "MYSQL_USER": "alertd", "MYSQL_PASSWORD": "x", "MYSQL_DATABASE": "alertd",
    }
    return subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30), backups


def test_a_complete_dump_becomes_a_backup(tmp_path):
    done, backups = _run(tmp_path, GOOD)
    assert done.returncode == 0, done.stderr
    files = list(backups.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("alertd-")
    assert files[0].name.endswith(".sql.gz")
    assert gzip.decompress(files[0].read_bytes()).decode().rstrip().endswith("-- Dump completed on 2026-11-15  2:00:11")
    assert "backup done" in done.stdout


@pytest.mark.parametrize(
    ("mysqldump", "why"),
    [(FAILS, "mysqldump exited with an error"), (TRUNCATED, "dump is incomplete")],
    ids=["mysqldump-fails", "dump-truncated"],
)
def test_a_failed_or_truncated_dump_leaves_nothing_and_exits_non_zero(tmp_path, mysqldump, why):
    done, backups = _run(tmp_path, mysqldump)
    assert done.returncode != 0
    assert why in done.stderr
    assert "backup done" not in done.stdout
    assert list(backups.iterdir()) == [], "no .sql.gz and no partial file may be left behind"


def test_a_failed_dump_does_not_rotate_good_backups_away(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    old = backups / "alertd-20200101T000000Z.sql.gz"
    old.write_bytes(gzip.compress(b"-- Dump completed"))
    os.utime(old, (0, 0))   # far older than BACKUP_KEEP_DAYS
    done, _ = _run(tmp_path, FAILS)
    assert done.returncode != 0
    assert old.exists(), "rotation must not run after a failed dump"


def test_leftovers_of_a_killed_run_are_removed(tmp_path):
    """Review K29: a run killed mid-dump (SIGKILL skips the trap) left an
    uncompressed .partial.sql that rotation never matched; the next run
    removes leftovers older than six hours (a manual run in progress is newer)."""
    backups = tmp_path / "backups"
    backups.mkdir()
    old = backups / "alertd-20261101T020000Z.sql.gz.partial.sql"
    fresh = backups / "alertd-20261115T020000Z.sql.gz.partial.sql"
    for f in (old, fresh):
        f.write_text("-- MySQL dump\n")
    os.utime(old, (1_700_000_000, 1_700_000_000))
    done, _ = _run(tmp_path, GOOD)
    assert done.returncode == 0, done.stderr
    assert not old.exists()
    assert fresh.exists()


# ── Scheduler (review K26) ────────────────────────────────────────────────
SCHEDULER = Path(__file__).resolve().parent.parent / "scripts" / "backup_scheduler.sh"


@pytest.mark.parametrize("shell", ["dash", "bash"])
@pytest.mark.parametrize(("field", "value", "match"), [
    ("*", "07", True), ("0", "00", True), ("2", "02", True), ("02", "2", True), ("08", "08", True),
    ("09", "08", False), ("*/15", "45", True), ("*/15", "50", False), ("*/5", "00", True),
    ("x", "05", False), ("*/0", "00", False),
])
def test_cron_fields_match_under_posix_sh(shell, field, value, match):
    probe = f'. "{SCHEDULER}"; cron_field_matches "$1" "$2"'
    done = subprocess.run([shell, "-c", probe, shell, field, value],
                          env={"BACKUP_SCHEDULER_LIB": "1", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert (done.returncode == 0) is match, (done.stdout, done.stderr)


def test_the_image_runs_the_tested_scheduler():
    dockerfile = (SCHEDULER.parent.parent / "Dockerfile.backup").read_text()
    assert "scripts/backup_scheduler.sh /usr/local/bin/entrypoint.sh" in dockerfile
    assert "10#" not in dockerfile
