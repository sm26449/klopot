#!/usr/bin/env bash
# rules_sim.sh — rule engine end to end over a real MQTT broker.
#
#   scripts/rules_sim.sh               # build the image from this checkout, run every scenario
#   scripts/rules_sim.sh --no-build    # reuse klopot:rulesim from a previous run
#   scripts/rules_sim.sh --keep        # leave the stack running afterwards (prints how to rerun)
#   SIM_ONLY=incident scripts/rules_sim.sh   # only scenarios whose name contains "incident"
#
# What it starts (and removes afterwards): a private Docker network, an empty
# MySQL 8, an anonymous Mosquitto 2 and the app image — a first install whose
# bootstrap admin key the driver (scripts/rules_sim.py) uses to import inputs,
# variables, templates and rules, then publishes MQTT messages and checks every
# rule's outcome (fires, no-data, errors, incidents, inhibition, auto-disable).
# Never touches any other container. Needs: docker, the .venv (paho-mqtt, httpx).
set -euo pipefail
cd "$(dirname "$0")/.."

BUILD=1; KEEP=0
for a in "$@"; do
  case "$a" in
    --no-build) BUILD=0 ;;
    --keep) KEEP=1 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

IMAGE=klopot:rulesim
ID="klopot-rulesim-$$"
NET="$ID-net"; DB="$ID-db"; MQ="$ID-mqtt"; APP="$ID-app"
cleanup() {
  [ "$KEEP" = 1 ] && return 0
  # One removal per container (no --rm): see scripts/_docker_build.sh.
  docker rm -f "$APP" "$MQ" "$DB" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [ "$BUILD" = 1 ]; then
  echo "== building $IMAGE from the checkout"
  # shellcheck source=scripts/_docker_build.sh
  . "$(dirname "$0")/_docker_build.sh"
  BUILD_QUIET=1 build_or_explain docker build -q -t "$IMAGE" . || exit 1
fi

free_port() {
  for p in $(seq "$1" "$2"); do
    if ! (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null; then echo "$p"; return 0; fi
  done
  return 1
}
APP_PORT=$(free_port 18200 18249) || { echo "no free port in 18200-18249" >&2; exit 1; }
MQ_PORT=$(free_port 18250 18299) || { echo "no free port in 18250-18299" >&2; exit 1; }

export SIM_URL="http://127.0.0.1:$APP_PORT"
export SIM_MQTT_PORT="$MQ_PORT"
export SIM_BROKER_HOST="$MQ"           # as the app sees it, inside the network
export SIM_ADMIN_KEY="alertd_rulesim_bootstrap_key_$$_0123456789"

echo "== starting MySQL, Mosquitto and a fresh install on $SIM_URL (broker 127.0.0.1:$MQ_PORT)"
docker network create "$NET" >/dev/null
docker run -d --name "$DB" --network "$NET" \
  -e MYSQL_ROOT_PASSWORD=sim-root -e MYSQL_DATABASE=alertd -e MYSQL_USER=alertd -e MYSQL_PASSWORD=sim-db \
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci >/dev/null
docker run -d --name "$MQ" --network "$NET" -p "127.0.0.1:$MQ_PORT:1883" \
  -v "$PWD/demo/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" eclipse-mosquitto:2 >/dev/null
for _ in $(seq 1 60); do
  docker exec "$DB" mysql -ualertd -psim-db -e 'SELECT 1' alertd >/dev/null 2>&1 && break
  sleep 2
done
# A low auto-disable threshold so the scenario that checks it runs in seconds.
docker run -d --name "$APP" --network "$NET" -p "127.0.0.1:$APP_PORT:5090" \
  -e ALERTD_DATABASE_URL="mysql+aiomysql://alertd:sim-db@$DB:3306/alertd" \
  -e ALERTD_MQTT_HOST="$MQ" -e ALERTD_MQTT_PORT=1883 \
  -e ALERTD_EVAL_ERROR_DISABLE_THRESHOLD=5 \
  -e ALERTD_BOOTSTRAP_ADMIN_KEY="$SIM_ADMIN_KEY" \
  "$IMAGE" >/dev/null
for _ in $(seq 1 90); do
  curl -sf "$SIM_URL/v1/health/ready" >/dev/null && break
  sleep 2
done
curl -sf "$SIM_URL/v1/health/ready" >/dev/null || { docker logs --tail 50 "$APP"; exit 1; }

status=0
.venv/bin/python scripts/rules_sim.py || status=$?
if [ "$status" != 0 ]; then
  echo "== last app log lines"; docker logs --tail 40 "$APP" 2>&1 | cut -c1-240
fi
if [ "$KEEP" = 1 ]; then
  echo "== kept: SIM_URL=$SIM_URL SIM_MQTT_PORT=$MQ_PORT SIM_BROKER_HOST=$MQ SIM_ADMIN_KEY=$SIM_ADMIN_KEY .venv/bin/python scripts/rules_sim.py"
  echo "   remove with: docker rm -f $APP $MQ $DB && docker network rm $NET"
fi
exit "$status"
