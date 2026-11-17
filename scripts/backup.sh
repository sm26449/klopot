#!/bin/sh
# alertd MySQL backup — runs from the backup sidecar.
#
# Behavior:
#   - mysqldump the alertd database to /backups/alertd-<UTC ISO>.sql.gz
#   - Keep ${BACKUP_KEEP_DAYS} days of backups (default 30); delete older.
#   - Exit non-zero if the dump fails or is incomplete, and leave no file
#     behind: a failed dump must never look like a backup.
#
# Required env (set on the sidecar in docker-compose.yml):
#   MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE, BACKUP_KEEP_DAYS
set -eu

: "${MYSQL_HOST:?MYSQL_HOST not set}"
: "${MYSQL_USER:?MYSQL_USER not set}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD not set}"
: "${MYSQL_DATABASE:?MYSQL_DATABASE not set}"
: "${BACKUP_KEEP_DAYS:=30}"
: "${BACKUP_DIR:=/backups}"

mkdir -p "$BACKUP_DIR"

# A run killed mid-dump (SIGKILL skips the trap below) leaves an uncompressed
# partial file that rotation never matches. Remove leftovers older than six
# hours — a run in progress, even one started by hand, is newer.
find "$BACKUP_DIR" -maxdepth 1 -name 'alertd-*.sql.gz.partial*' -mmin +360 -delete 2>/dev/null || true

stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/alertd-$stamp.sql.gz"
raw="$out.partial.sql"
tmp="$out.partial"

# Whatever goes wrong below, no half-written file stays in the backup dir.
trap 'rm -f "$raw" "$tmp"' EXIT

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup start → $out"

# --single-transaction → consistent snapshot without locking writes
# --routines / --triggers → dump stored programs (we don't use any yet,
#                            but cheap insurance for future schema changes)
# Not `mysqldump | gzip`: the pipeline's status is gzip's, so a dump that
# failed (server down, wrong password, disk full) still produced a tiny valid
# .sql.gz, "backup done" and exit 0 — and rotation went on deleting the good
# ones.
# The password goes through MYSQL_PWD (this process's environment), never as
# --password=: an argument is visible to every user of the host in `ps`
# (2026-11-17 improvements review, IP-11) — as in the compose healthcheck.
if ! MYSQL_PWD="$MYSQL_PASSWORD" mysqldump \
    --host="$MYSQL_HOST" \
    --user="$MYSQL_USER" \
    --single-transaction \
    --routines \
    --triggers \
    --no-tablespaces \
    --add-drop-database \
    --databases "$MYSQL_DATABASE" \
    > "$raw"
then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup FAILED: mysqldump exited with an error" >&2
    exit 1
fi

# mysqldump ends a complete dump with this comment; a dump cut short has none.
if ! tail -n 1 "$raw" | grep -q '^-- Dump completed'; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup FAILED: dump is incomplete (no 'Dump completed' line)" >&2
    exit 1
fi

gzip -9 < "$raw" > "$tmp"
rm -f "$raw"
mv "$tmp" "$out"

size=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out" 2>/dev/null || echo "?")
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup done size=${size}"

# Rotate — anything older than KEEP_DAYS (mtime-based)
deleted=$(find "$BACKUP_DIR" -name 'alertd-*.sql.gz' -mtime +"$BACKUP_KEEP_DAYS" -print -delete | wc -l)
if [ "$deleted" -gt 0 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] rotated $deleted old backup(s) (keep=${BACKUP_KEEP_DAYS}d)"
fi
