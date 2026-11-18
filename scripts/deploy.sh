#!/usr/bin/env bash
# deploy.sh — upgrade a running docker-compose install to the checked-out code,
# with a verified backup and an image rollback tag taken first.
#
#   scripts/deploy.sh <label>            # asks for confirmation before changing anything
#   scripts/deploy.sh <label> --yes      # no prompt (for scripted use)
#   scripts/deploy.sh <label> --dry-run  # preflight + plan only, changes nothing
#   scripts/deploy.sh <label> --runtime-dir=DIR   # deploy into a separate runtime directory
#
# <label> names this deploy (e.g. "f4", "1.9.0"): it goes into the backup file
# name and the rollback image tag `rollback-pre-<label>`.
#
# Two layouts:
#   in-repo (default) — .env and the compose project live in this checkout;
#                       the image is built with `docker compose build alertd`.
#   runtime dir       — --runtime-dir=DIR or KLOPOT_RUNTIME_DIR=DIR: .env, compose
#                       files and backups/ live in DIR, the code in this checkout.
#                       The image is built from the checkout as <repo>:<label>
#                       and KLOPOT_IMAGE in DIR/.env is pointed at it (the old
#                       .env is saved to DIR/backups first).
#
# Steps:
#   1. Preflight   — containers up, current health / schema / row counts
#   2. Backup      — mysqldump of the app database to backups/alertd-predeploy-<label>-<UTC>.sql.gz, gzip-verified
#   3. Rollback tag — tag the image the running container uses as rollback-pre-<label>
#   4. Build       — see the two layouts above
#   5. Recreate    — docker compose up -d --no-deps alertd   (MySQL is not touched;
#                    migrations run automatically on startup)
#   6. Verify      — wait for /v1/health/ready, compare schema revision and row
#                    counts with step 1, scan the startup log for errors
#
# With an external database (compose.external-db.yml) there is no `mysql`
# compose service: set ALERTD_MYSQL_CONTAINER to the MySQL container's name.
#
# Apart from KLOPOT_IMAGE in runtime-dir mode, it does NOT push, pull or change
# .env. If a new release needs a new env var, add it to .env AND to the
# `environment:` list in docker-compose.yml first — compose passes only the
# variables listed there. In runtime-dir mode the preflight warns when the
# runtime's compose configuration does not pass a setting the checkout's does
# (an old copy of docker-compose.yml there).
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"

LABEL=""; YES=0; DRY=0; RT="${KLOPOT_RUNTIME_DIR:-}"
for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    --dry-run) DRY=1 ;;
    --runtime-dir=*) RT="${a#*=}" ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown option: $a" >&2; exit 2 ;;
    *) LABEL="$a" ;;
  esac
done
[[ "$LABEL" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "usage: scripts/deploy.sh <label> [--yes|--dry-run] [--runtime-dir=DIR]" >&2; exit 2; }

say() { printf '\n== %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

if [ -n "$RT" ]; then
  [ -d "$RT" ] || die "runtime dir not found: $RT"
  RT="$(cd "$RT" && pwd)"
  [ "$RT" != "$SRC" ] || RT=""
fi
cd "${RT:-$SRC}"   # compose project, .env and backups/ live here

[ -f .env ] || die ".env not found in $PWD (deploying from a checkout without .env? pass --runtime-dir=DIR)"
envval() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }
if [ -n "$RT" ]; then
  grep -qE '^KLOPOT_IMAGE=' .env || die "KLOPOT_IMAGE not set in $RT/.env (runtime-dir mode needs it)"
fi

# Containers are resolved through compose (honours COMPOSE_FILE in .env);
# override with ALERTD_CONTAINER / ALERTD_MYSQL_CONTAINER (name or id).
APP="${ALERTD_CONTAINER:-$(docker compose ps -q alertd 2>/dev/null || true)}"
DB="${ALERTD_MYSQL_CONTAINER:-$(docker compose ps -q mysql 2>/dev/null || true)}"
# shellcheck source=scripts/_klopot_url.sh
. "$SRC/scripts/_klopot_url.sh"
# shellcheck source=scripts/_docker_build.sh
. "$SRC/scripts/_docker_build.sh"
# shellcheck source=scripts/_compose_drift.sh
. "$SRC/scripts/_compose_drift.sh"
URL="$(klopot_url)"   # the port of the install in $PWD, from its .env
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-180}"

DB_NAME="$(envval MYSQL_DATABASE)"; DB_NAME="${DB_NAME:-alertd}"
ROOT_PW="$(envval MYSQL_ROOT_PASSWORD)"; [ -n "$ROOT_PW" ] || die "MYSQL_ROOT_PASSWORD not set in .env"

sql() { docker exec -e MYSQL_PWD="$ROOT_PW" "$DB" mysql -uroot -N -B "$DB_NAME" -e "$1"; }
snapshot() {
  sql "SELECT CONCAT('alembic=', version_num) FROM alembic_version;
       SELECT CONCAT('rules=', COUNT(*)) FROM rules;
       SELECT CONCAT('templates=', COUNT(*)) FROM templates;
       SELECT CONCAT('channels=', COUNT(*)) FROM channels;
       SELECT CONCAT('inputs=', COUNT(*)) FROM inputs;
       SELECT CONCAT('api_keys=', COUNT(*)) FROM api_keys;" | tr '\n' ' '
}
http() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$URL$1" || true; }

# ── 1. Preflight ──────────────────────────────────────────────────
say "Preflight"
[ -n "$APP" ] && docker inspect "$APP" >/dev/null 2>&1 || die "alertd container not found (fresh install? use scripts/bootstrap.sh)"
[ -n "$DB" ] && docker inspect "$DB" >/dev/null 2>&1 || die "mysql container not found (external database? set ALERTD_MYSQL_CONTAINER)"
echo "source:   $SRC  $(git -C "$SRC" log --oneline -1)"
echo "runtime:  ${RT:-(in-repo)}"
if [ -n "$(git -C "$SRC" status --porcelain)" ]; then
  echo "WARNING: working tree has uncommitted changes — they WILL be built into the image:"
  git -C "$SRC" status --short | head -10
fi
BEFORE="$(snapshot)"
OLD_IMAGE="$(docker inspect --format '{{.Image}}' "$APP")"
OLD_REF="$(docker inspect --format '{{.Config.Image}}' "$APP")"
IMAGE_REPO="$(sed 's/:[^:/]*$//' <<<"$OLD_REF")"
ROLLBACK_TAG="$IMAGE_REPO:rollback-pre-$LABEL"
NEW_IMAGE="$IMAGE_REPO:$LABEL"
echo "running:  $(curl -s -m 5 "$URL/v1/version" || echo '?')  image $OLD_REF (${OLD_IMAGE:7:12})"
echo "ready:    HTTP $(http /v1/health/ready)"
echo "state:    $BEFORE"
PENDING="$(ls "$SRC"/alembic/versions/*.py | sed -E 's/.*_([0-9]{4})_.*/\1/' | sort | tail -1)"
echo "migrations: database at ${BEFORE%% *}, code head is $PENDING"
if [ -n "$RT" ]; then
  # A runtime dir keeps its own copy of docker-compose.yml. An old copy does
  # not pass the settings added since: a value in .env for them never reaches
  # the container (2026-11-18: ALERTD_LATITUDE and four older ones).
  MISSING="$(docker compose config 2>/dev/null | compose_missing_settings "$SRC/docker-compose.yml" || true)"
  if [ -n "$MISSING" ]; then
    echo
    echo "WARNING: $RT's compose configuration does not pass these settings into the container"
    echo "         (its docker-compose.yml is older than the checkout's); a value in .env for them is ignored:"
    printf '           %s\n' $MISSING
    echo "         Update it (keep the old one):"
    echo "           cp -p $RT/docker-compose.yml $RT/backups/docker-compose.yml-$LABEL && cp $SRC/docker-compose.yml $RT/"
  elif ! cmp -s "$SRC/docker-compose.yml" docker-compose.yml; then
    echo "note: $RT/docker-compose.yml differs from the checkout's (every setting is passed)"
  fi
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="backups/alertd-predeploy-$LABEL-$TS.sql.gz"
echo
if [ -n "$RT" ]; then
  echo "Plan: backup → $RT/$OUT ; rollback tag → $ROLLBACK_TAG ; build $NEW_IMAGE from $SRC ;"
  echo "      KLOPOT_IMAGE=$NEW_IMAGE in $RT/.env ; recreate $APP"
else
  echo "Plan: backup → $OUT ; rollback tag → $ROLLBACK_TAG ; build ; recreate $APP"
fi
if [ "$DRY" = 1 ]; then echo "(dry run — nothing changed)"; exit 0; fi
if [ "$YES" != 1 ]; then
  read -r -p "Deploy to the running service now? [y/N] " ans
  [[ "$ans" =~ ^[yY]$ ]] || { echo "aborted."; exit 1; }
fi

# ── 2. Backup ─────────────────────────────────────────────────────
say "Backup"
mkdir -p backups
docker exec -e MYSQL_PWD="$ROOT_PW" "$DB" mysqldump -uroot --single-transaction --routines \
  --no-tablespaces --databases "$DB_NAME" | gzip > "$OUT.partial"
gzip -t "$OUT.partial" || die "backup failed gzip verification"
[ "$(stat -c %s "$OUT.partial")" -gt 10000 ] || die "backup is suspiciously small"
mv "$OUT.partial" "$OUT"
echo "backup:   $PWD/$OUT ($(du -h "$OUT" | cut -f1))"

# ── 3. Rollback tag ───────────────────────────────────────────────
say "Rollback tag"
docker tag "$OLD_IMAGE" "$ROLLBACK_TAG"
echo "tagged:   $ROLLBACK_TAG → ${OLD_IMAGE:7:12}"

rollback_help() {
  echo
  echo "To roll back the code:"
  if [ -n "$RT" ]; then
    echo "  cd $RT && sed -i 's|^KLOPOT_IMAGE=.*|KLOPOT_IMAGE=$ROLLBACK_TAG|' .env && docker compose up -d --no-deps alertd"
  else
    echo "  docker tag $ROLLBACK_TAG $IMAGE_REPO:latest && docker compose up -d --no-deps alertd"
  fi
  echo "If this deploy applied a migration, the old code may refuse the newer schema —"
  echo "then also restore the database (docs/DEPLOY.md, \"Backups\"):"
  echo "  $PWD/$OUT"
}

# ── 4. Build ──────────────────────────────────────────────────────
say "Build"
if [ -n "$RT" ]; then
  build_or_explain docker build -t "$NEW_IMAGE" "$SRC" || die "build failed — the running service was not touched"
  cp -p .env "backups/env-predeploy-$LABEL-$TS"
  sed -i "s|^KLOPOT_IMAGE=.*|KLOPOT_IMAGE=$NEW_IMAGE|" .env
  echo "KLOPOT_IMAGE: $OLD_REF → $NEW_IMAGE (old .env: $PWD/backups/env-predeploy-$LABEL-$TS)"
else
  build_or_explain docker compose build alertd || die "build failed — the running service was not touched"
fi

# ── 5. Recreate ───────────────────────────────────────────────────
say "Recreate $APP (MySQL untouched)"
SINCE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker compose up -d --no-deps alertd 2>&1 | tail -3
APP="${ALERTD_CONTAINER:-$(docker compose ps -q alertd)}"   # recreated: new id

# ── 6. Verify ─────────────────────────────────────────────────────
say "Waiting for $URL/v1/health/ready (up to ${READY_TIMEOUT_SEC}s)"
deadline=$((SECONDS + READY_TIMEOUT_SEC)); code=""
while (( SECONDS < deadline )); do
  code="$(http /v1/health/ready)"
  [ "$code" = 200 ] && break
  sleep 3
done
if [ "$code" != 200 ]; then
  echo "NOT READY after ${READY_TIMEOUT_SEC}s (last HTTP $code). Last log lines:"
  docker logs "$APP" --since "$SINCE" 2>&1 | tail -30
  rollback_help
  exit 1
fi

AFTER="$(snapshot)"
echo "running:  $(curl -s -m 5 "$URL/v1/version")  image $(docker inspect --format '{{.Image}}' "$APP" | cut -c8-19)"
echo "before:   $BEFORE"
echo "after:    $AFTER"
rc=0
if [ "${BEFORE#* }" != "${AFTER#* }" ]; then
  echo "WARNING: config row counts changed across the deploy — investigate."; rc=1
fi
ERRS="$(docker logs "$APP" --since "$SINCE" 2>&1 | grep -ciE 'traceback|\bERROR\b|CRITICAL' || true)"
if [ "$ERRS" != 0 ]; then
  echo "WARNING: $ERRS error line(s) in the startup log:"
  docker logs "$APP" --since "$SINCE" 2>&1 | grep -iE 'traceback|\bERROR\b|CRITICAL' | head -10
  rc=1
fi
rollback_help
if [ "$rc" = 0 ]; then say "Deploy OK"; else say "Deployed, with warnings above"; fi
exit "$rc"
