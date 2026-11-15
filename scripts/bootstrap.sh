#!/usr/bin/env bash
#
# bootstrap.sh — fresh-install alertd end-to-end, from a clean host to a
# running service. Idempotent: safe to re-run on an existing install.
#
#   1. Preflight: .env present, docker + compose available
#   2. (traefik variant) check the external proxy network exists
#   3. docker compose up -d --build  (migrations + bootstrap seed run
#      automatically inside the container lifespan)
#   4. Wait for /v1/health/ready on the port this install publishes
#      (KLOPOT_HTTP_PORT in .env, default 5090)
#   5. If a site-specific scripts/restore_config_seed.sh exists, run it and
#      restart alertd; a public install has none and starts empty
#
# Usage:  bash scripts/bootstrap.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=scripts/_klopot_url.sh
. scripts/_klopot_url.sh
ALERTD_URL="$(klopot_url)"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-120}"

say() { printf '\n== %s\n' "$*"; }

# ── 1. Preflight ──────────────────────────────────────────────────
[ -f .env ] || {
  echo "ERROR: .env not found. Run:  cp .env.example .env  and edit it" >&2
  echo "       (at minimum: MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD, the MQTT broker," >&2
  echo "       ALERTD_ADMIN_BOOTSTRAP_PASSWORD and any channel secrets)." >&2
  exit 1
}
command -v docker >/dev/null || { echo "ERROR: docker not installed." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: docker compose v2 required." >&2; exit 1; }

# ── 2. Proxy network (traefik variant only) ───────────────────────
TRAEFIK_NETWORK="$(sed -n 's/^TRAEFIK_NETWORK=//p' .env | head -1)"
if [ -n "$TRAEFIK_NETWORK" ] && ! docker network inspect "$TRAEFIK_NETWORK" >/dev/null 2>&1; then
  echo "ERROR: TRAEFIK_NETWORK=$TRAEFIK_NETWORK does not exist — start traefik first" >&2
  exit 1
fi

# ── 3. Build + start ──────────────────────────────────────────────
say "docker compose up -d --build (migrations + bootstrap seed run on startup)"
docker compose up -d --build

# ── 4. Wait for health ────────────────────────────────────────────
wait_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT_SEC))
  while (( SECONDS < deadline )); do
    if curl -sf -m 3 "$ALERTD_URL/v1/health/ready" >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  echo "ERROR: $ALERTD_URL/v1/health/ready not answering after ${HEALTH_TIMEOUT_SEC}s." >&2
  echo "       Check: docker compose logs alertd" >&2
  return 1
}
say "Waiting for alertd to be ready on $ALERTD_URL/v1/health/ready"
wait_healthy

# ── 5. Operator config seed (site install only) ───────────────────
# The operator's seed scripts are site-specific and live in the private config
# repo, not in the public tree. Load them when present; a fresh public install
# simply skips to a running, empty service you populate yourself.
if [ -f scripts/restore_config_seed.sh ]; then
  say "Loading operator config seed (rules / templates / channels / routing)"
  bash scripts/restore_config_seed.sh

  # ── 6. Reload rules ─────────────────────────────────────────────
  say "Restarting alertd to reload rules into the evaluator"
  docker compose restart alertd >/dev/null
  wait_healthy
else
  say "No operator seed present — starting with an empty configuration"
  echo "   Install a ready-made pack in the admin UI (Packs) or with"
  echo "   POST $ALERTD_URL/v1/packs/apply (docs/PACKS.md), or build rules yourself."
fi

say "Done. Health:"
curl -s -m 5 "$ALERTD_URL/v1/health"
echo
echo "Next steps:"
echo "  - docker compose ps                    # containers up"
echo "  - open $ALERTD_URL/admin/              # admin UI (needs ALERTD_ADMIN_UI_ENABLED=true)"
echo "  - docs/GETTING_STARTED.md to configure your first alert; docs/DEPLOY.md for details"
