# Klopot — Getting Started

**Languages:** **English** · [Română](GETTING_STARTED.ro.md) ·
[← Back to README](../README.md)

This guide explains the core concepts and walks you from a fresh
instance to a working alert — both through the **admin UI** and through
the **API**. For the full endpoint reference see
**[docs/API.md](API.md)**.

## The mental model

alertd is a small pipeline you configure declaratively:

```
inputs ──▶ variables ──▶ rules ──▶ (template) ──▶ channels ──▶ delivery
(MQTT,      (named        (when       (how it      (where it     (outbox +
 HTTP,       values        is this     looks:        goes:         retry
 webhook,    from the      true?)      title,        telegram,     worker)
 SMS)        inputs)                   message,      sms, ui,
                                       severity)     webhook…)
```

- **Input** — a declared source of raw data (an MQTT topic, an HTTP
  endpoint polled on an interval, an inbound webhook, incoming SMS, an
  Alertmanager / Grafana receiver).
- **Variable** — a named value derived from inputs and kept in a live
  cache. Sources: `mqtt` (a topic → value), `aggregate`
  (sum/avg/min/max over several topics), `constant`, `computed` (a
  formula over other variables) and `schedule` (a value set on a cron).
- **Rule** — a boolean **condition** over variables (e.g.
  `room_temp > 30`). It fires its template after the condition holds
  for `persist_n` consecutive evaluations (debounce).
- **Template** — how a notification of a given **type** looks: title,
  message (both rendered from the context/variables), severity, icon,
  cooldown, quiet hours.
- **Channel** — a delivery destination: UI WebSocket, Telegram, SMS,
  email, Web Push, MQTT, ntfy, Gotify, Pushover, or a generic webhook.
- **Route** — which channels a template sends to (with an optional
  minimum severity and per-route config overrides).
- **Schedule** — fire a template on a cron (e.g. a daily summary).
- **Snooze** — mute a type, a rule, or a channel for a while.

You don't *have* to use rules. The simplest integration is an external
caller that already knows *when* to alert and just calls `POST /v1/fire`
with a `type` — alertd owns the routing, rendering, gating and delivery.

## Two ways to fire

1. **Externally, by type.** Your app/script/Node-RED detects a
   condition and calls `POST /v1/fire`. You only configure the template,
   channels and route in alertd.
2. **Internally, by rule.** You declare inputs + variables + a rule, and
   alertd evaluates it continuously and fires on its own.

---

## Walkthrough A — fire by type (API)

The fastest way to send your first notification. You need an API key
with `admin` (to configure) and `fire` (to send) — the bootstrap admin
key has both.

```bash
HOST=http://localhost:5090
KEY=alertd_your_admin_key

# 1. A channel — the in-app UI channel (no secrets, safe to test with).
#    A fresh install already has ui_default (409 if it exists): skip this then.
curl -X POST $HOST/v1/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"ui_default","kind":"ui","config":{}}'

# 2. A template for a "demo_alert" type
curl -X POST $HOST/v1/templates -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"demo_alert","severity":"warning",
       "title_template":"Demo: {what}",
       "message_template":"Value is {value}.","min_repeat_min":0}'

# 3. Route demo_alert → ui_default (routing lives in the config pack)
cat > route.yaml <<'YAML'
routes:
  - template: demo_alert
    channel: ui_default
    severity_min: info
YAML
curl -X POST "$HOST/v1/config/import?apply=true" -H "X-API-Key: $KEY" \
  -H "Content-Type: application/yaml" --data-binary @route.yaml

# 4. Fire it
curl -X POST $HOST/v1/fire -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"demo_alert","context":{"what":"test","value":42}}'
```

You should get `{"status":"sent","channels":["ui_default"],…}`. Watch it
land live:

```bash
# via the log
curl -H "X-API-Key: $KEY" "$HOST/v1/log?limit=1&type=demo_alert"
# or the live stream (open the admin UI, or a WS client)
```

To send to **Telegram** instead, create a telegram channel (its
`config` needs a bot token and chat id — see `GET /v1/meta/kinds` for
the fields; keep secrets in env via `*_ref` fields) and route to it.

---

## Walkthrough B — fire by rule (continuous evaluation)

Let alertd watch a value and fire on its own.

```bash
# 1. An MQTT input (your broker)
curl -X POST $HOST/v1/inputs -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"home_mqtt","kind":"mqtt","config":{"host":"mosquitto"}}'

# 2. A variable from a topic
curl -X POST $HOST/v1/variables -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"room_temp","source":"mqtt","input_id":<ID_FROM_STEP_1>,
       "config":{"topic":"sensors/room/temperature","type":"number","stale_after_sec":120}}'

# 3. A rule: fire "room_too_hot" when room_temp > 30 for 3 ticks
curl -X POST $HOST/v1/rules -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"room_too_hot_rule","template_type":"room_too_hot",
       "condition_expr":"room_temp > 30","persist_n":3,"eval_interval_sec":10}'
```

Create a `room_too_hot` template + route as in Walkthrough A. Now when
the broker publishes `sensors/room/temperature` above 30 for three evaluations, alertd
fires automatically. See **[the expression language](EXPRESSION_LANGUAGE.md)**
for what you can write in `condition_expr` (comparisons, boolean logic,
`var_age()`, filters, etc.).

---

## Using the admin UI

Everything above is also doable at **`/admin`** (log in with the admin
account). After the first sign-in a new installation opens the **Setup**
guide: pick a channel kind, save it and get a test send, then choose what to
watch (your own scripts, an MQTT sensor or heartbeat pack, Alertmanager).
The pages:

1. **Channels** → *New channel* → pick a kind, fill the fields (secrets
   go in via "Use env ref").
2. **Templates** → *New template* → type, severity, title/message
   templates, cooldown — and tick the channel(s) under **Routing —
   channels**: a template with no channel ticked delivers nothing.
3. **Rules** → *New rule* → template type, condition, persist count.
4. **Inputs / Variables** → declare your sources and the values pulled
   from them.
5. **Alerts log** → watch fires live, filter, acknowledge; the live
   feed updates over WebSocket.
6. **Snooze & maintenance** → mute a type/rule/channel, or enable
   maintenance mode (`*`).
7. **Config import/export** → back up or move the whole configuration;
   Templates, Rules and Variables also have an *Actions* menu to export or
   import part of it.
8. **Packs** → install a ready-made set (service heartbeat, sensor
   threshold, Alertmanager…) by filling in its settings.
9. **Activity** → what reached Klopot and what it sent to each provider.

**Ctrl+K** (⌘K) searches pages, templates, rules, variables, channels,
inputs and packs.

The UI builds its forms from `GET /v1/meta/kinds`, so it always matches
the server's accepted fields.

---

## What happens when a fire is sent

1. The template is loaded; if none exists the fire is logged as
   `unknown_type` (a safe no-op).
2. **Gating:** disabled? snoozed? throttled (within `min_repeat_min`)?
   quiet hours? below the template's delivery gate? inhibited by another active
   rule? A recent duplicate to coalesce onto? If gated, the row is
   logged with a `suppressed_reason` and nothing is sent.
3. **Persist first:** the log row + one delivery row per routed channel
   are committed **before** any send.
4. **Deliver:** a synchronous first attempt is made. Channels that fail
   with a retryable error stay `pending`; the background worker retries
   them with backoff. Status rolls up to
   `sent`/`partial`/`pending`/`failed` (see
   [API › Delivery & outbox](API.md#delivery--outbox-semantics)).

Everything is visible in the **Alerts log** and `GET /v1/log`, and every
config change is in the **Audit** log.

## Next steps

- **[API Reference](API.md)** — every endpoint with examples.
- **[Expression language](EXPRESSION_LANGUAGE.md)** — rule syntax.
- **[Deploy & Operations](DEPLOY.md)** — env vars, backups, upgrades.
- **[Architecture](ARCHITECTURE.md)** — the internals.
