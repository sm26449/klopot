# Packs

A **pack** is a ready-to-install piece of configuration — inputs, variables,
templates, rules, routes, channels, schedules — with a short header that names
it and declares the few values every installation must choose (a broker
address, a topic, a threshold, the channel to alert on). Klopot ships a small
catalog; you can export any part of your own configuration as a pack and
install it on another instance, or keep it as a backup.

A pack is the same YAML document as `GET /v1/config/export` plus a `pack:`
header. Everything that works for config import (validation, cross-reference
checks, per-item preview with overwrite / skip / copy, one transaction) works
for packs.

## Format

```yaml
pack:
  id: service-heartbeat                 # ^[a-z][a-z0-9-]{1,63}$, unique in the catalog
  name: Service heartbeat               # or {en: "...", ro: "..."}
  description: Alert when a service stops publishing its heartbeat.
  version: 1.0.0                        # of the pack, not of Klopot
  tags: [uptime, mqtt]
  parameters:
    - name: broker_host                 # ^[a-z][a-z0-9_]*$, used as ${broker_host}
      label: MQTT broker host           # or {en, ro}
      description: Hostname or IP of the broker the service publishes to.
      type: string                      # string | number | integer | boolean | env | channel
      default: mqtt.example.com
      required: true
    - name: alert_channel
      label: Send alerts to
      type: channel                     # the UI offers the existing channels
      default: ui_default

version: "1.0"
inputs:
  - name: heartbeats_mqtt
    kind: mqtt
    config: {host: "${broker_host}", port: "${broker_port}"}
routes:
  - {template: service_down, channel: "${alert_channel}"}
```

### Parameters

| `type` | Accepts | Notes |
|--------|---------|-------|
| `string` | any text | |
| `number` | int or float | |
| `integer` | whole number | |
| `boolean` | true / false | |
| `env` | an environment variable name (`^[A-Z_][A-Z0-9_]*$`) | for `*_ref` fields — a pack never carries a secret value. Use `KLOPOT_SECRET_<NAME>` (put in `secrets.env`, docs/DEPLOY.md); the preview reports for each one whether Klopot may read it and whether it is set |
| `channel` | a channel name | must exist after the install (an existing channel, or one the pack creates) |

A parameter without a `default` is required unless `required: false`.

### Substitution

Applied to every string **value** in the document body (keys and the header
are not substituted), before validation:

- A value that is exactly `"${name}"` takes the parameter's **typed** value —
  `port: "${broker_port}"` becomes the integer `1883`.
- Inside a longer string, `${name}` is replaced by the text of the value —
  `"sensors/${room}/temperature"`.
- `$${` writes a literal `${`.
- A `${name}` that is not a declared parameter is an error; so is a declared
  parameter that the body never uses (likely a typo).

Template placeholders (`{name}`) and rule expressions are untouched — only
`${…}` is a pack parameter.

## Installing

- **Admin UI → Packs:** the catalog, or upload / paste a pack file. Fill the
  parameters → preview (every item: new / identical / differs) → choose
  overwrite / skip / copy for items that already exist → install.
- **API:** `POST /v1/packs/preview` and `POST /v1/packs/apply`, each with
  either `pack_id` (catalog) or `yaml` (your file), plus `params`; apply also
  takes `decisions` and `default_existing`, exactly like
  `/v1/config/import/apply`. See `docs/API.md`.

A pack with parameters cannot go through `/v1/config/import` (its `${…}` would
be imported literally); a pack without parameters can.

## Exporting

`GET /v1/config/export` with a selection (`sections`, `names`, `category`,
`with_dependencies=true`) and `pack_id` (+ optional `pack_name`,
`pack_description`, `pack_version`) returns a pack. With dependencies the
selection is closed over everything it needs:

| Selected | Brings along |
|----------|--------------|
| rule | its template(s) (firing and resolved), the variables it reads, the rules named in `inhibited_by` |
| variable | the input it reads (`mqtt` / `aggregate`), the variables a computed formula reads (transitively) |
| template | its routes |
| route | its channel |
| schedule | its template |

Secrets are always masked in a pack export: only `*_ref` environment
variable names leave the instance. An exported pack has no parameters; add
them by hand where an installation must differ (hosts, topics, thresholds).

## The built-in catalog

Shipped in the image under `app/packs/`:

| Pack | What it sets up |
|------|-----------------|
| `self-monitoring` | Klopot's own alerts (rule auto-disabled, daily digest, restore drill). Installed automatically on first start. |
| `service-heartbeat` | MQTT heartbeat → critical alert when it goes stale. |
| `sensor-threshold` | MQTT numeric sensor → alert above a threshold for N checks. |
| `alertmanager` | Alertmanager / Grafana receiver with templates per severity. |
| `script-alerts` | `script_info` / `script_warning` / `script_critical` templates showing the `title` and `message` a script sends to `POST /v1/fire`. Used by the setup guide's "my scripts" path. |
| `seplos-bms` | Seplos BMS V3 batteries read by [seplos-modbus-mqtt](https://github.com/sm26449/seplos-modbus-mqtt): state of charge low / critical, temperature high / critical, cell imbalance, packs not reporting, collector offline. Thresholds become constant variables. |
| `fronius-inverter` | Fronius (SunSpec) inverters read by [fronius-modbus-mqtt](https://github.com/sm26449/fronius-modbus-mqtt): fault, overvoltage warning / critical, not responding during daylight, throttling (installed disabled), collector offline, no inverter responding. **Install once per inverter**; the collector-wide items are shared. |
| `openvigil-nvr` | Templates for every alert [OpenVigil](https://github.com/sm26449/openvigil) sends through `POST /v1/fire` (2.2+; 2.1 sends only fall detection), including the recovery templates of its episodes. The messages show OpenVigil's own `text`, so they read right in its language. |
| `multi-bus-gateway` | Templates for every alert [Multi-Bus Gateway](https://github.com/sm26449/multi-bus-gateway) sends through `POST /v1/fire` — the same set as its own export (`GET /api/alerts/alertd-pack`), plus the three condition templates for rules you write. Paired alerts (device, sink, device alarm, bridge, virtual meter, rules engine) arrive as episodes: the recovery closes the episode and Klopot sends its `_ok` template once. |

The four packs above come from a real installation, rewritten against what
each project publishes or sends (not against that installation's topics),
in English and without channels or contact data. Two notes from that
review: a MQTT collector that publishes **on change only** cannot be judged
by a reading's age — these packs gate on the collector's heartbeat instead —
and SunSpec operating state **4 is MPPT** (normal production); throttled is 5,
fault 7 — but an idle Fronius also reports 7 after dark, so the fault rule
only alerts in daylight. `tests/packs/test_catalog_rules.py` runs every catalog rule against
scenarios (fires on its condition, stays silent otherwise and before any
data arrives).

To add one: a file `app/packs/<id>.yaml` in this format;
`tests/api/test_packs_api.py` installs every catalog pack with its defaults on
an empty database, so a broken pack fails the build.
