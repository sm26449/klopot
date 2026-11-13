# Example: service uptime (heartbeat staleness)

A minimal "is my service alive?" setup. A service publishes a heartbeat value
to MQTT every ~30 seconds; alertd raises a **critical** alert when that value
goes stale (no update for 90 s), delivered to the built-in `ui_default`
channel — so this pack needs no external channel.

## What it declares

| Kind | Name | Purpose |
|------|------|---------|
| input (mqtt) | `heartbeats_mqtt` | connects to your broker |
| variable | `api_heartbeat` | the heartbeat topic, stale after 90 s |
| template | `service_down` | the critical alert text |
| rule | `api_no_heartbeat` | fires when `var_age('api_heartbeat') > 90` twice |
| route | → `ui_default` | shows it in the admin UI / log |

## Import

```bash
KEY=alertd_your_api_key
BASE=https://host        # your alertd base URL

# Validate (dry run) — reports what it would create, writes nothing:
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/yaml' \
     --data-binary @examples/uptime/uptime.yaml \
     "$BASE/v1/config/import"

# Apply:
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/yaml' \
     --data-binary @examples/uptime/uptime.yaml \
     "$BASE/v1/config/import?apply=true"
```

## Customise

- `host` — your MQTT broker.
- `topic` — the heartbeat topic your service publishes to.
- `stale_after_sec` and the rule's `> 90` — your tolerance for "down".
- Add a `telegram` / `webhook` channel and a second `route` to get paged.
