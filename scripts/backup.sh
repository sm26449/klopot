#!/bin/sh
# alertd MySQL backup — runs from the backup sidecar.
#
# Behavior:
#   - mysqldump the alertd database to /backups/alertd-<UTC ISO>.sql.gz
#   - Keep ${BACKUP_KEEP_DAYS} days of backups (default 30); delete older.
#   - Exit non-zero if dump fails so the cron line surfaces the failure.
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

stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/alertd-$stamp.sql.gz"
tmp="$out.partial"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup start → $out"

# --single-transaction → consistent snapshot without locking writes
# --routines / --triggers → dump stored programs (we don't use any yet,
#                            but cheap insurance for future schema changes)
mysqldump \
    --host="$MYSQL_HOST" \
    --user="$MYSQL_USER" \
    --password="$MYSQL_PASSWORD" \
    --single-transaction \
    --routines \
    --triggers \
    --no-tablespaces \
    --add-drop-database \
    --databases "$MYSQL_DATABASE" \
    | gzip -9 > "$tmp"

mv "$tmp" "$out"

size=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out" 2>/dev/null || echo "?")
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup done size=${size}"

# Rotate — anything older than KEEP_DAYS (mtime-based)
deleted=$(find "$BACKUP_DIR" -name 'alertd-*.sql.gz' -mtime +"$BACKUP_KEEP_DAYS" -print -delete | wc -l)
if [ "$deleted" -gt 0 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] rotated $deleted old backup(s) (keep=${BACKUP_KEEP_DAYS}d)"
fi
