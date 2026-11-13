# Example: IoT sensor threshold → ntfy

An MQTT sensor publishes a numeric reading; alertd fires when it crosses a
threshold and pushes the alert to your phone through [ntfy](https://ntfy.sh)
via a webhook channel using the built-in **ntfy preset**.

## What it declares

| Kind | Name | Purpose |
|------|------|---------|
| input (mqtt) | `sensors_mqtt` | connects to your broker |
| channel (webhook) | `ntfy_alerts` | POSTs the message to an ntfy topic |
| variable | `freezer_temp_c` | the sensor topic, numeric |
| template | `freezer_too_warm` | the alert text, with the live value |
| rule | `freezer_temp_high` | fires when `freezer_temp_c > -10` three times |
| route | → `ntfy_alerts` | pushes it to ntfy |

## Import

```bash
KEY=alertd_your_api_key
BASE=https://host

curl -H "X-API-Key: $KEY" -H 'Content-Type: application/yaml' \
     --data-binary @examples/iot-threshold/iot-threshold.yaml \
     "$BASE/v1/config/import?apply=true"
```

Then subscribe to the topic on your phone (the ntfy app) or in a browser at
`https://ntfy.sh/<your-topic>`.

## Customise

- `url` — your ntfy topic, `https://ntfy.sh/<your-topic>` (pick an
  unguessable name; anyone with the URL can read it, or self-host ntfy).
- `host` / `topic` — your broker and the sensor topic.
- `condition_expr` — the threshold and comparison.
- `persist_n` / `eval_interval_sec` — how long the condition must hold before
  it fires (debounce).
