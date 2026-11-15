#!/usr/bin/env bash
#
# restore_drill.sh — prove the latest backup actually restores.
#
# "You don't have backups, you have hope" — until a restore has been
# tested. This drill (audit 2026-07-06, gap #5):
#
#   1. picks the newest backups/alertd-*.sql.gz
#   2. boots a THROWAWAY MySQL 8.0 container (tmpfs datadir, no ports,
#      no networks shared with the stack — production is never touched)
#   3. restores the dump into it
#   4. verifies: alembic_version matches the LIVE schema revision, and
#      every config + state table restored with a sane row count
#   5. reports the verdict through alertd itself (templates
#      restore_drill_ok / restore_drill_failed) so the result lands in
#      the normal notification pipeline; falls back to stdout/exit code
#      if no API key is available
#   6. always removes the throwaway container
#
# Run manually or from host cron (monthly), e.g.:
#   15 03 1 * *  cd /opt/klopot && bash scripts/restore_drill.sh >> backups/drill.log 2>&1
#
# Env overrides: BACKUP_DIR, DRILL_IMAGE, ALERTD_URL, LIVE_MYSQL, ALERTD_API_KEY
# (a key with the `fire` scope; without one the verdict goes to stdout only).
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
DRILL_IMAGE="${DRILL_IMAGE:-mysql:8.0}"
# shellcheck source=scripts/_klopot_url.sh
. scripts/_klopot_url.sh
ALERTD_URL="$(klopot_url)"
LIVE_MYSQL="${LIVE_MYSQL:-$(docker compose ps -q mysql 2>/dev/null || true)}"
NAME="alertd-restore-drill-$$"

# Tables that must exist and be non-empty after restore (config),
# plus tables that must merely exist (state may legitimately be small).
REQUIRED_NONEMPTY="channels templates variables rules template_channels settings"
REQUIRED_PRESENT="notifications_log rule_state throttle_state snooze audit_log api_keys alembic_version"

report() { # $1 = ok|failed, $2 = detail message
    echo "== DRILL ${1^^}: $2"
    if [ -n "${ALERTD_API_KEY:-}" ]; then
        curl -sf -m 10 -X POST "$ALERTD_URL/v1/fire" \
            -H "X-API-Key: $ALERTD_API_KEY" -H 'Content-Type: application/json' \
            -d "{\"type\":\"restore_drill_$1\",\"context\":{\"detail\":\"$2\",\"backup\":\"$(basename "${LATEST:-none}")\"},\"source\":\"restore-drill\"}" \
            >/dev/null || echo "   (reporting to alertd failed — check manually)"
    fi
}

cleanup() {
    docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
    report failed "$1"
    exit 1
}

# ── 1. Newest backup ───────────────────────────────────────────────
LATEST=$(ls -1t "$BACKUP_DIR"/alertd-*.sql.gz 2>/dev/null | head -1 || true)
[ -n "$LATEST" ] || fail "no backup found in $BACKUP_DIR"
AGE_H=$(( ($(date +%s) - $(stat -c %Y "$LATEST")) / 3600 ))
echo "== drill backup: $LATEST (age ${AGE_H}h)"
[ "$AGE_H" -le 48 ] || fail "newest backup is ${AGE_H}h old (>48h) — is the backup sidecar dead?"

# ── 2. Throwaway MySQL ─────────────────────────────────────────────
echo "== starting throwaway $DRILL_IMAGE container ($NAME)"
docker run -d --name "$NAME" --rm \
    --network none \
    --tmpfs /var/lib/mysql \
    -e MYSQL_ROOT_PASSWORD=drill \
    "$DRILL_IMAGE" >/dev/null

for i in $(seq 1 60); do
    # A real query with the password, not `mysqladmin ping`: ping also succeeds
    # against the image's init-time server, before root's password exists, and
    # the restore then fails with "Access denied" — reported as a corrupt dump.
    if docker exec "$NAME" mysql -uroot -pdrill -e 'SELECT 1' >/dev/null 2>&1; then
        break
    fi
    [ "$i" -lt 60 ] || fail "throwaway MySQL never became ready (120s)"
    sleep 2
done
echo "== throwaway MySQL ready"

# ── 3. Restore ─────────────────────────────────────────────────────
echo "== restoring $(basename "$LATEST")"
if ! restore_err=$(zcat "$LATEST" | docker exec -i "$NAME" mysql -uroot -pdrill 2>&1 >/dev/null); then
    fail "restore errored: $(basename "$LATEST"): $(printf '%s' "$restore_err" | grep -v 'Using a password' | tail -1)"
fi

# ── 4. Verify ──────────────────────────────────────────────────────
q() { docker exec "$NAME" mysql -uroot -pdrill -N -e "$1" 2>/dev/null; }
qlive() { docker exec "$LIVE_MYSQL" mysql -ualertd -palertd -N -e "$1" 2>/dev/null; }

live_rev=$(qlive "SELECT version_num FROM alertd.alembic_version;" || echo "?")
drill_rev=$(q "SELECT version_num FROM alertd.alembic_version;" || echo "!")
# A backup naturally lags live right after a deploy that migrated —
# on a real restore, alertd's startup runs `alembic upgrade head`
# automatically. So: the restored revision must be KNOWN to the
# current codebase (present in alembic/versions/); only an unknown
# (future/divergent) revision is a failure.
if [ "$drill_rev" = "$live_rev" ]; then
    echo "== alembic revision OK ($drill_rev)"
elif grep -qrE "^revision(: str)? = [\"']${drill_rev}[\"']" alembic/versions/; then
    echo "== alembic revision OK ($drill_rev — older than live $live_rev; startup migration would upgrade it)"
else
    fail "restored alembic revision '$drill_rev' unknown to this codebase (live=$live_rev) — backup from a divergent schema?"
fi

summary=""
for t in $REQUIRED_NONEMPTY; do
    n=$(q "SELECT COUNT(*) FROM alertd.$t;") || fail "table $t missing after restore"
    [ "$n" -gt 0 ] || fail "table $t restored EMPTY"
    summary="$summary $t=$n"
done
for t in $REQUIRED_PRESENT; do
    q "SELECT COUNT(*) FROM alertd.$t;" >/dev/null || fail "table $t missing after restore"
done
echo "== row counts:$summary"

report ok "restored $(basename "$LATEST"), rev=$drill_rev,$summary"
echo "== drill PASSED"
