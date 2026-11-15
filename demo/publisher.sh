#!/bin/sh
# Emit a sine wave (amplitude 15) to demo/sine every 2s, so it repeatedly
# crosses the demo rule's threshold of 5 and triggers an alert.
set -eu
i=0
while true; do
  v=$(awk "BEGIN{ printf \"%.2f\", 15 * sin($i / 3.0) }")
  mosquitto_pub -h mosquitto -t demo/sine -m "$v"
  echo "published demo/sine = $v"
  i=$((i + 1))
  sleep 2
done
