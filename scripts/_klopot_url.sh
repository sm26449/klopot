# shellcheck shell=bash
# Sourced by bootstrap.sh, deploy.sh and restore_drill.sh (not run on its own).
#
# klopot_url — the base URL of THIS install's API: $ALERTD_URL when set,
# else 127.0.0.1 on KLOPOT_HTTP_PORT from ./.env (the compose default 5090).
# With a fixed 5090 a script waited on, and reported the health of, whatever
# else listened there — another install. Run it from the directory that holds
# the install's .env.
klopot_url() {
  if [ -n "${ALERTD_URL:-}" ]; then
    printf '%s\n' "$ALERTD_URL"
    return
  fi
  local port
  port="$(sed -n 's/^KLOPOT_HTTP_PORT=//p' .env 2>/dev/null | tail -1 | tr -d "\"'[:space:]" || true)"
  printf 'http://127.0.0.1:%s\n' "${port:-5090}"
}
