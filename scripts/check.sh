#!/usr/bin/env bash
# check.sh — run locally what CI runs, so failures show up before a push.
#
#   scripts/check.sh            # ruff, mypy (baseline), pytest (SQLite), node, OpenAPI + SDK drift, gitleaks
#   scripts/check.sh --mysql    # the above + the MySQL gate against a throwaway MySQL 8
#   scripts/check.sh --e2e      # the above + browser end-to-end tests (scripts/e2e.sh: Docker + Playwright)
#   scripts/check.sh --fast     # ruff + pytest only
#
# Uses the project virtualenv (.venv, falling back to venv). Nothing here touches
# the running service or its database: the MySQL gate starts its own disposable
# container on a random localhost port and removes it afterwards.
set -uo pipefail

cd "$(dirname "$0")/.."

MYSQL=0; FAST=0; E2E=0
for a in "$@"; do
  case "$a" in
    --mysql) MYSQL=1 ;;
    --fast)  FAST=1 ;;
    --e2e)   E2E=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

if   [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif [ -x venv/bin/python ];  then PY=venv/bin/python
else
  echo "ERROR: no virtualenv. Create one:" >&2
  echo "  python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 2
fi

failed=()
step() {  # step <name> <command...>
  local name="$1"; shift
  printf '\n== %s\n' "$name"
  if "$@"; then echo "-- ok: $name"; else echo "-- FAILED: $name"; failed+=("$name"); fi
}

mypy_baseline() {
  # mypy exits non-zero while printing the baseline errors; the filter is the gate.
  "$PY" -m mypy app > mypy-report.txt || true
  "$PY" -m mypy_baseline filter < mypy-report.txt
}

openapi_drift() {
  # Regenerate into a temp copy so the working tree is never modified.
  local tmp; tmp="$(mktemp)"
  "$PY" -c "
import json, sys
sys.path.insert(0, '.')
from app.main import create_app
json.dump(create_app().openapi(), open('$tmp', 'w'), indent=2, sort_keys=True)
open('$tmp', 'a').write('\n')
" || { rm -f "$tmp"; return 1; }
  if cmp -s "$tmp" openapi/v1.json; then rm -f "$tmp"; return 0; fi
  echo "openapi/v1.json is stale — run: $PY scripts/dump_openapi.py  (then commit it)"
  diff <("$PY" -m json.tool openapi/v1.json) <("$PY" -m json.tool "$tmp") | head -20
  rm -f "$tmp"; return 1
}

gitleaks_scan() {
  # Same image and flags as the CI `gitleaks` job: full git history + working tree.
  docker run --rm -v "$PWD:/repo:ro" zricethezav/gitleaks:v8.21.2 \
    detect --source /repo --config /repo/.gitleaks.toml --redact --no-banner
}

mysql_gate() {
  local name="alertd-check-mysql-$$" port
  docker run -d --rm --name "$name" -p 127.0.0.1::3306 --tmpfs /var/lib/mysql \
    -e MYSQL_ROOT_PASSWORD=test -e MYSQL_DATABASE=alertd \
    -e MYSQL_USER=alertd -e MYSQL_PASSWORD=alertd \
    mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci >/dev/null || return 1
  # shellcheck disable=SC2064
  trap "docker rm -f $name >/dev/null 2>&1" RETURN EXIT
  port="$(docker port "$name" 3306/tcp | head -1 | sed 's/.*://')"
  echo "throwaway MySQL: $name on 127.0.0.1:$port"
  local ok=0
  for _ in $(seq 1 60); do
    if docker exec "$name" mysql -ualertd -palertd -e 'SELECT 1' alertd >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  [ "$ok" = 1 ] || { echo "MySQL never became ready"; return 1; }
  ALERTD_TEST_DATABASE_URL="mysql+aiomysql://alertd:alertd@127.0.0.1:$port/alertd" \
    ALERTD_MQTT_HOST="" "$PY" -m pytest -q -p no:cacheprovider -m "not sqlite"
}

step "ruff" "$PY" -m ruff check app scripts
if [ "$FAST" = 0 ]; then step "mypy (baseline)" mypy_baseline; fi
step "pytest (SQLite)" env ALERTD_MQTT_HOST="" "$PY" -m pytest -q -p no:cacheprovider -m "not mysql"
if [ "$FAST" = 0 ]; then
  if command -v node >/dev/null; then
    step "admin-ui node tests" bash -c 'node --test tests/js/*.mjs 2>&1 | grep -E "^# (tests|pass|fail)|^not ok"; exit "${PIPESTATUS[0]}"'
  else
    echo; echo "== admin-ui node tests: SKIPPED (node not installed)"
  fi
  step "OpenAPI drift" openapi_drift
  if command -v npx >/dev/null && [ -d node_modules/openapi-typescript ]; then
    step "SDK drift" scripts/generate_sdks.sh --check
  else
    echo; echo "== SDK drift: SKIPPED (run npm ci)"
  fi
  if command -v docker >/dev/null; then
    step "gitleaks" gitleaks_scan
  else
    echo; echo "== gitleaks: SKIPPED (docker not installed)"
  fi
fi
if [ "$MYSQL" = 1 ]; then step "pytest (MySQL gate)" mysql_gate; fi
if [ "$E2E" = 1 ]; then step "browser e2e" scripts/e2e.sh; fi

echo
if [ "${#failed[@]}" -gt 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "All checks passed."
