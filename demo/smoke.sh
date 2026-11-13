#!/usr/bin/env bash
# Demo smoke: Klopot must deliver one notification to the sink within 2 minutes.
#
# Assumes `docker compose -f compose.demo.yml up -d` is running and has exposed
# Klopot on 127.0.0.1:8090 and the sink on 127.0.0.1:8091.
set -euo pipefail

KLOPOT="http://127.0.0.1:${DEMO_KLOPOT_PORT:-8090}"
SINK="http://127.0.0.1:${DEMO_SINK_PORT:-8091}"
KEY="${ALERTD_BOOTSTRAP_ADMIN_KEY:-alertd_demo_key_please_change}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "1/3 waiting for Klopot to be healthy…"
for _ in $(seq 1 60); do
  if curl -fsS "$KLOPOT/v1/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$KLOPOT/v1/health" | grep -q '"status":"ok"' || { echo "Klopot not healthy"; exit 1; }

echo "2/3 importing the demo config pack…"
curl -fsS -H "X-API-Key: $KEY" -H 'Content-Type: application/yaml' \
     --data-binary "@$HERE/config.yaml" \
     "$KLOPOT/v1/config/import?apply=true" >/dev/null

echo "3/3 waiting (<=120s) for the sink to receive a notification…"
for _ in $(seq 1 60); do
  n=$(curl -fsS "$SINK/count" | sed -E 's/.*"count": *([0-9]+).*/\1/')
  if [ "${n:-0}" -ge 1 ]; then
    echo "OK — sink received $n notification(s). Demo works."
    exit 0
  fi
  sleep 2
done

echo "FAILED — no notification reached the sink within 2 minutes."
exit 1
