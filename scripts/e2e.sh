#!/usr/bin/env bash
# e2e.sh — browser end-to-end tests against a throwaway Klopot install.
#
#   scripts/e2e.sh                 # build the image from this checkout, run tests/e2e/*.e2e.mjs
#   scripts/e2e.sh --no-build      # reuse klopot:e2e from a previous run
#   scripts/e2e.sh --keep          # leave the stack running afterwards (prints its URL)
#   E2E_ONLY=mobile scripts/e2e.sh # only test files whose name contains "mobile"
#   E2E_AFTER=<command>            # run <command> on the stack after the tests pass, before
#                                  # it is removed (env: E2E_URL, E2E_PASSWORD, E2E_ADMIN_KEY,
#                                  # E2E_BOOTSTRAP_PASSWORD, E2E_NETWORK, E2E_IMAGE); with
#                                  # E2E_ONLY=none no test runs first (scripts/screenshots.sh)
#
# What it starts (and removes afterwards): a private Docker network, an empty
# MySQL 8 and the app image on a free 127.0.0.1 port — exactly a first install:
# bootstrap admin password (forced change at first login) plus a bootstrap admin
# API key the tests use to seed data. Never touches any other container.
# Needs: docker, node ≥ 22 (see .nvmrc), `npm ci` (Playwright), Chromium (installed on demand).
set -euo pipefail
cd "$(dirname "$0")/.."

BUILD=1; KEEP=0
for a in "$@"; do
  case "$a" in
    --no-build) BUILD=0 ;;
    --keep) KEEP=1 ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

IMAGE=klopot:e2e
ID="klopot-e2e-$$"
NET="$ID-net"; DB="$ID-db"; APP="$ID-app"
cleanup() {
  [ "$KEEP" = 1 ] && return 0
  docker rm -f "$APP" "$DB" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

[ -d node_modules/playwright ] || { echo "run npm ci first (Playwright)" >&2; exit 1; }
npx --no-install playwright install chromium >/dev/null 2>&1 || npx --no-install playwright install --with-deps chromium

if [ "$BUILD" = 1 ]; then
  echo "== building $IMAGE from the checkout"
  # shellcheck source=scripts/_docker_build.sh
  . "$(dirname "$0")/_docker_build.sh"
  BUILD_QUIET=1 build_or_explain docker build -q -t "$IMAGE" . || exit 1
fi

port=""
for p in $(seq 18100 18199); do
  if ! (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null; then port=$p; break; fi
done
[ -n "$port" ] || { echo "no free port in 18100-18199" >&2; exit 1; }

export E2E_URL="http://127.0.0.1:$port"
export E2E_BOOTSTRAP_PASSWORD="e2e-Bootstrap-$$-pass"
export E2E_PASSWORD="e2e-Chosen-$$-passphrase"
export E2E_ADMIN_KEY="alertd_e2e_bootstrap_key_$$_0123456789"

echo "== starting a fresh install on $E2E_URL"
docker network create "$NET" >/dev/null
# No --rm on either container: cleanup() removes them once (and --keep keeps
# them); two removals racing broke BuildKit's cache (scripts/_docker_build.sh).
docker run -d --name "$DB" --network "$NET" \
  -e MYSQL_ROOT_PASSWORD=e2e-root -e MYSQL_DATABASE=alertd -e MYSQL_USER=alertd -e MYSQL_PASSWORD=e2e-db \
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci >/dev/null
for _ in $(seq 1 60); do
  docker exec "$DB" mysql -ualertd -pe2e-db -e 'SELECT 1' alertd >/dev/null 2>&1 && break
  sleep 2
done
docker run -d --name "$APP" --network "$NET" -p "127.0.0.1:$port:5090" \
  -e ALERTD_DATABASE_URL="mysql+aiomysql://alertd:e2e-db@$DB:3306/alertd" \
  -e ALERTD_MQTT_HOST="" -e ALERTD_COOKIE_SECURE=false -e ALERTD_ADMIN_UI_ENABLED=true \
  -e ALERTD_ADMIN_BOOTSTRAP_PASSWORD="$E2E_BOOTSTRAP_PASSWORD" \
  -e ALERTD_BOOTSTRAP_ADMIN_KEY="$E2E_ADMIN_KEY" \
  "$IMAGE" >/dev/null
for _ in $(seq 1 90); do
  curl -sf "$E2E_URL/v1/health/ready" >/dev/null && break
  sleep 2
done
curl -sf "$E2E_URL/v1/health/ready" >/dev/null || { docker logs "$APP" | tail -30; exit 1; }

rc=0
if [ "${E2E_ONLY:-}" = none ] && [ -n "${E2E_AFTER:-}" ]; then
  echo "== no tests (E2E_ONLY=none): the fresh install goes to E2E_AFTER as is"
else
  files=$(ls tests/e2e/*.e2e.mjs | grep -- "${E2E_ONLY:-}" || true)
  [ -n "$files" ] || { echo "no e2e test files match '${E2E_ONLY:-}'" >&2; exit 1; }
  echo "== running $(echo "$files" | wc -w) e2e file(s)"
  # Files run in name order (00_first_run must go first: it sets the password).
  node --test --test-reporter=tap --test-concurrency=1 $files || rc=$?
fi
if [ "$rc" = 0 ] && [ -n "${E2E_AFTER:-}" ]; then
  echo "== after: $E2E_AFTER"
  E2E_NETWORK="$NET" E2E_IMAGE="$IMAGE" bash -c "$E2E_AFTER" || rc=$?
fi
if [ "$KEEP" = 1 ]; then
  echo "stack kept: $E2E_URL — rerun a file with:"
  echo "  E2E_URL=$E2E_URL E2E_PASSWORD=$E2E_PASSWORD E2E_ADMIN_KEY=$E2E_ADMIN_KEY node --test --test-reporter=tap tests/e2e/<file>"
  echo "remove it: docker rm -f $APP $DB; docker network rm $NET"
fi
exit "$rc"
