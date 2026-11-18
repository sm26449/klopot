# shellcheck shell=bash
# compose_missing_settings — the ALERTD_* settings the checkout's compose file
# passes into the container but the runtime's effective configuration does not
# (a runtime dir with an old copy of docker-compose.yml: a value set in .env
# for those never reaches Klopot). Sourced by deploy.sh.
#
#   docker compose config | compose_missing_settings /path/to/checkout/docker-compose.yml
#
# Prints one name per line, nothing when the runtime passes them all. Reads
# `docker compose config` output on stdin (so it is testable without Docker).
compose_missing_settings() {
  local checkout="$1" want have
  want="$(grep -oE '^[[:space:]]+ALERTD_[A-Z0-9_]+:' "$checkout" | tr -d ' :\t' | sort -u)"
  have="$(grep -oE '^[[:space:]]+ALERTD_[A-Z0-9_]+:' | tr -d ' :\t' | sort -u)"
  [ -n "$have" ] || return 0     # no config to compare (compose failed): say nothing
  comm -23 <(printf '%s\n' "$want") <(printf '%s\n' "$have")
}
