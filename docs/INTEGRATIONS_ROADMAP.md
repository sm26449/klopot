# Integrations roadmap

Status: Proposed · Date: 2026-11-08

What the service can talk to today, what is missing for it to be a
credible general-purpose notification layer, and — for each gap —
enough design to start the work without a second planning round.

Conventions used below:

- **Shape**: `channel` (output), `input` (data source), `both`, or
  `platform` (auth, SDK, packaging).
- **Effort**: S ≈ half a day, M ≈ 1–2 days, L ≈ 3–5 days, including
  tests and docs.
- **Files**: the checklist from [`EXTENSIBILITY.md`](EXTENSIBILITY.md)
  always applies: adapter module, `kind` in `app/schemas/common.py` and
  `app/db/models.py`, field metadata in `app/meta_kinds.py`, registry
  entry, a migration widening the enum, a happy-path test, an entry in
  `API.md`. Only *extra* files are listed per item.
- Every channel adapter implements `BaseChannel.send(notif, config,
  idempotency_key=…)` and returns `SendResult`; retries, breakers and
  rate limits are the manager's job. Every input adapter implements
  `BaseInput.start/stop/health` and pushes `(topic, payload, kind)`
  through the value callback.

---

## 0. Current surface

| Shape | Kinds | Notes |
|-------|-------|-------|
| Channels | `ui`, `banner`, `telegram`, `sms`, `email`, `push`, `webhook` | Webhook presets: Discord, Slack, Teams, Mattermost, Home Assistant, ntfy, generic |
| Inputs | `mqtt`, `http_poll`, `webhook`, `schedule`, `sms_inbox` | `email_imap` exists in the enum only; no adapter |
| Platform | `X-API-Key` scopes, browser sessions, OpenAPI at `/docs`, Prometheus `/v1/metrics` | No SSO, no SDK, no Grafana dashboard |

Observations that drive the priorities:

1. MQTT is the primary input, yet there is **no MQTT output**. Anyone
   running Home Assistant, Node-RED or a second service cannot consume
   notifications the same way they feed values in.
2. There is no way to **ingest from Prometheus / Grafana**, which is
   where most potential users already have alerts defined.
3. Telegram is the most used human channel and it is **one-way**:
   acknowledging or snoozing means opening the admin UI.
4. Escalation exists (`app/core/escalation.py`) but every channel at the
   end of it is a silent notification. There is no **intrusive**
   channel (voice, emergency-priority push).
5. There is no **external-event lifecycle**. A delivery is identified
   by its outbox row; nothing stores the provider's message id, no
   inbound receipt or action is deduplicated, and "acknowledge" is a
   local flag. Every bidirectional integration below (1.3, 1.4
   Pushover, 2.1) needs that foundation first — see §5.

---

## 1. Tier 1 — start here (unlock the public audience)

### 1.1 MQTT output channel — `kind: mqtt` · channel · **S**

**Why.** Closes the loop with the ecosystem the service already lives
in. Home Assistant gets native `mqtt` sensors/notifications, Node-RED
gets a topic, a second instance can chain.

**Design.**
- Config: `topic_template` (default `klopot/notifications/{type}`),
  `qos` (0|1|2, default 1), `retain` (bool, default false),
  `payload_template` (same `{title}` / `| jsonstr` filter language as
  the webhook channel; default JSON = the `Notification` dataclass plus
  `delivery_id`), `broker` (`default` = the engine's broker from
  settings, or an explicit `host/port/username/password/tls` block).
- There is no single "engine client": the input manager owns one
  connection *per named MQTT input* (`app/inputs/mqtt.py`). The channel
  therefore takes either `input_ref: <mqtt input name>` (publish over
  that input's connection, which the manager exposes through a
  `publish()` hook) or an explicit `broker` block, in which case the
  channel owns a persistent connection of its own with reconnect.
- Health: connection up. Idempotency: include `idempotency_key` in the
  payload as `delivery_id`; QoS 1/2 deduplicate at the transport only,
  not application-level outbox retries, so subscribers should key on
  `delivery_id`. Retained messages are off by default because a
  retained alert re-fires subscribers on reconnect.
- Also publish a retained `klopot/<instance>/status` availability topic
  (`online`, LWT `offline`), scoped by instance id. It reports
  *connection* loss, not evaluator health; the engine's own heartbeat
  (tick age) is a separate topic published on each tick.

**Files.** `app/channels/mqtt.py`, a hook in `app/core/manager.py` to
expose the shared client, preset `home_assistant_mqtt` in
`meta_kinds.py`. Tests: publish captured by a fake client; template
rendering; LWT set.

### 1.2 Alertmanager / Grafana receiver — `kind: alertmanager` · input · **M**

**Why.** Turns the service into the notification layer for anyone who
already has Prometheus or Grafana alerting. It is the cheapest way to
reach users outside the IoT niche.

**Design.**
- Endpoint: `POST /v1/inputs/{id}/webhook` (already exists for
  `webhook` inputs) with a body parser for the Alertmanager v4 webhook
  schema (`alerts[]`, `labels`, `annotations`, `status`, `startsAt`,
  `endsAt`, `fingerprint`). Grafana unified alerting emits a compatible
  payload with a few extra fields; accept both.
- Mapping, per alert in the group (groups are mixed: handle each
  alert's own `status`):
  - `type` = `labels.<type_label>` (default `alertname`) **if a template
    of that type exists**, else the input's `default_type`, which must
    be a configured generic template (`alertmanager_alert`) whose body
    renders `{annotations.summary}` / `{labels.instance}`. Unknown alert
    names must never be dropped silently.
  - Severity today comes from the stored template, not from the fire.
    The input therefore maps `labels.severity` to a **template choice**
    (`type_by_severity: {critical: am_critical, warning: am_warning,
    default: am_info}`) rather than overriding a field that `/v1/fire`
    does not accept. If per-fire severity override is wanted later, it
    is an API change with its own validation.
  - `context` = labels + annotations flattened with dotted keys; the
    renderer's `_lookup` resolves exact dotted keys first, so
    `{labels.instance}` works unchanged.
  - **Identity.** `FireEnvelope.idempotency_key` exists but is not used
    by the dispatcher today; making it durable is part of §5. The
    receiver's identity is `(input_id, fingerprint, startsAt)` stored as
    an *episode*, valid beyond the normal 5-minute dedup window, so
    Alertmanager's repeat sends of a still-firing group coalesce for
    the whole episode.
  - `status: firing` → fire through the shared fire service (routing,
    gating, dedup unchanged).
  - `status: resolved` → **is not an acknowledgement**. Persist a
    resolution on the episode (`resolved_at`, `resolved_by=alertmanager`),
    stop escalation for it, and, if the template declares
    `resolved_template_type`, fire a resolution notice. A resolution
    whose `startsAt` is older than the episode's current one is
    ignored so a delayed resolve cannot close a newer episode. The
    operator's ack stays a separate, human action.
  - Bounds: cap alerts per request (default 200), honour
    `truncatedAlerts` by logging a warning and firing a single
    `alertmanager_truncated` notice, reject bodies over 1 MB.
- Auth: the existing input `auth_required` / bearer token on the
  webhook input (`tests/inputs/test_webhook_auth_f35.py` covers it).
- Optional: also register each alert as a state-cache variable
  (`am.<alertname>.<instance> = 1|0`) so rules can combine Prometheus
  alerts with MQTT values.

**Files.** `app/inputs/alertmanager.py` (parser + mapper, pure
functions), reuse of `app/api/v1/fire.py` internals via a shared
service function (refactor `fire()` call site out of the route first),
a migration for `notifications_log.acked_by` if it does not take a free
string. Tests: fixture payloads from Alertmanager 0.27 and Grafana 11;
firing/resolved round trip; dedup across repeated group sends.

### 1.3 Telegram acknowledge / snooze buttons · both · **M** (after §5)

**Why.** The operator at 02:00 reads the alert on the phone; today the
only way to acknowledge or snooze is the admin UI. Inline buttons make
the most used channel bidirectional.

**Design.**
- Outgoing: `telegram` channel gains `inline_actions: bool`
  (default true). `send()` attaches `reply_markup` with `Ack`,
  `Snooze 1h`, `Snooze until morning`. Each button carries an **opaque
  action token**: a random 128-bit id stored in an `action_tokens`
  table with `(delivery_id, action, expires_at, bot_id, used_at)`.
  An HMAC scheme in 64 bytes of `callback_data` would leave too few
  bits for both the id and a useful tag; a stored token is simpler,
  revocable and expires (default 24 h). The sent message's
  `(chat_id, message_id)` is persisted on the delivery (§5 provider
  reference) so the message can be edited later.
- Incoming: new input `kind: telegram_updates`. Two modes:
  `webhook` (Telegram POSTs to `/v1/inputs/{id}/webhook`, verified
  with `X-Telegram-Bot-Api-Secret-Token`; the webhook route must learn
  this kind and this header — today it accepts only `webhook`/`sms_inbox`
  kinds and `X-Input-Token`, `app/api/v1/inputs.py`) or `long_poll`
  (`getUpdates`, for deployments behind NAT, offset persisted).
  Exactly one receiver per bot token; the input refuses to start if
  another input already owns that bot. Updates are deduplicated by
  `update_id`.
- Authorisation, both conditions required: the callback's
  `message.chat.id` **must equal the chat the delivery was sent to**,
  and the tapping user must satisfy the channel's actor policy —
  `allowed_user_ids` when set, otherwise any member of that chat
  (explicit opt-in `any_chat_member: true`). "User allowlist OR chat
  match" would let any group member bypass the allowlist. Unauthorised
  taps get `answerCallbackQuery(text="not allowed")` and are audited.
- Effect: ack → the shared ack service, snooze → `POST /v1/snooze`
  scoped to the notification's type; both are **durable commands** (§5)
  so a crash between Telegram's callback and the DB write cannot lose
  or double-apply them. Then edit the original message to append
  `✓ acked by <first_name>` and remove the keyboard. Audit actor =
  `telegram:<user_id>`.
- Escalation (`escalation.py`) already stops on ack, so this closes the
  loop for criticals.

**Files.** `app/channels/telegram.py` (keyboard), `app/inputs/telegram_updates.py`,
`app/core/channel_actions.py` (token issue/consume + dispatch to
ack/snooze), migration for `action_tokens`, `meta_kinds.py`,
`app/api/v1/inputs.py` (kind + header). Tests: expired/used/foreign
token, wrong chat, unlisted user, ack round trip with a fake Bot API,
duplicate `update_id`, long-poll offset across restart.

### 1.4 First-class push services: ntfy, Gotify, Pushover · channel · **S each**

**Why.** ntfy already works as a webhook preset, but severity → priority
mapping and tags are lost. Pushover's *emergency* priority (repeat
until acknowledged) is the intrusive channel the escalation path is
missing. Gotify is the self-hoster's default.

**Design (shared).** A small `priority_map` helper translating
`info/warning/critical` to each service's scale; `title` and `message`
sent as native fields; `icon` → ntfy `Tags` / Gotify `extras`.
- **ntfy**: `server_url`, `topic`, `token` (write-only), `priority_map`
  (default 2/3/5), `click_url` (link back to `/admin/#/log?id=`),
  `actions` = `view` button to the admin UI. Idempotency: ntfy has no
  dedup; keep at-least-once.
- **Gotify**: `server_url`, `app_token` (write-only), priority 2/5/8.
- **Pushover**: `user_key`, `app_token` (write-only), `device`
  optional, priority -1/0/1 by severity. **Emergency priority (2) is an
  explicit opt-in** (`emergency_for: [critical]`, default off) with
  `retry=60` `expire=3600`; Pushover caps emergency retries at 50.
  Every emergency send returns a `receipt` that is **persisted** on
  the delivery (§5) — without it an ambiguous timeout can start two
  emergency loops. Acknowledgement in Klopot calls the receipts API
  to cancel the retries; acknowledgement in the Pushover app reaches
  us either via the `callback` URL (`pushover_receipts` input, with
  Pushover's own payload parsing and verification) or, behind NAT, by
  polling `receipts/<id>.json` for open receipts.

**Files.** `app/channels/ntfy.py`, `gotify.py`, `pushover.py`. Keep the
ntfy **webhook preset** as a compatibility path for existing
configurations; the native kind is additive.

---

## 2. Tier 2 — on-call and chat ecosystems

### 2.1 PagerDuty Events API v2 (and JSM Operations compatibility) · channel · **M** (after §5)

**Why.** The on-call name any ops team asks about. It has a native
dedup key and acknowledge/resolve verbs that map onto an *episode*,
not onto a delivery.

**Design.** `routing_key` (write-only), `event_action: trigger` on the
first fire of an episode, `dedup_key` = the **episode key** from §5
(stable across repeat fires of the same alert, not the per-delivery
idempotency key — transport identity and incident identity differ).
Repeat fires for an open episode send `trigger` again with the same
`dedup_key` (PagerDuty merges). Acknowledge/resolve in Klopot emit
`acknowledge` / `resolve` with that same key as **durable outbound
lifecycle commands** (§5), targeting the routing key the episode was
opened with even if the channel config changed since. Severity maps to
`critical/error/warning/info` via a configurable table.

**Opsgenie.** The standalone product shuts down on 5 April 2027 (Atlassian migration notice); Atlassian states the
`api.opsgenie.com` alert ingestion endpoints continue for Jira Service
Management customers. Treat this as a demand-driven "JSM Operations
(Opsgenie API) compatibility" item built on the same lifecycle
commands, not as a launch feature, and do not describe the API as
disappearing.

### 2.2 Matrix · channel · **S–M**

`homeserver_url`, `access_token` (write-only), `room_id`; send
`m.notice` with both `body` and `formatted_body` (HTML). Health =
`/_matrix/client/v3/account/whoami`. Transaction id = `idempotency_key`
(Matrix dedups on it natively — the only chat protocol that does).

### 2.3 Signal via `signal-cli-rest-api` · channel · **S**

`api_url`, `number`, `recipients[]`. Plain HTTP POST; attach the
severity icon as the first character. Document that the container must
run next to the service; no cloud API exists.

### 2.4 Voice call with TTS (Twilio, with Vonage as second provider) · channel · **M**

**Why.** The last rung of escalation. A phone that rings is the only
channel that reliably wakes someone.

**Design.** `provider`, `account_sid`, `auth_token` (write-only),
`from_number`, `to_numbers[]` (called in order until one answers —
this *is* an on-call rotation in miniature), `tts_template` (default:
`"{severity} alert. {title}. Press 1 to acknowledge."`). Twilio needs
a public TwiML URL: serve `GET /v1/channels/{id}/twiml/{notif_id}` and
`POST .../gather` for the DTMF ack (same ack service as 1.3). Rate
limit default 2/min. Mark the kind `intrusive=true` in `meta_kinds` so
the UI warns when routing non-critical templates to it.

### 2.5 WhatsApp Business Cloud API · channel · **M**, low priority

Only pre-approved *template* messages may be sent outside a 24-hour
user-initiated window, so the channel config must name a Meta template
and map our fields to its parameters. Useful for some operators,
painful to onboard; do it after 2.4.

---

## 3. Tier 3 — inputs

### 3.1 Modbus TCP · input · **M**

**Why.** The origin domain (inverters, meters, BMS) speaks Modbus; so
do HVAC, pumps and PLCs in every other industrial niche. Today those
values must be bridged through MQTT by another service.

**Design.** `pymodbus` (async client). Config: `host`, `port`, `unit_id`,
`poll_interval_sec`, `registers[]` each with `name`, `address`,
`function` (`holding|input|coil|discrete`), `type`
(`u16|s16|u32|s32|f32`), `byte_order`, `scale`, `offset`. Each register
becomes a state-cache value `modbus.<input>.<name>`; the adapter is
"critical" like MQTT (an unreachable device sets the input unhealthy
and a built-in freshness rule can fire). Backoff on connection loss.
Tests with a `pymodbus` simulator server in-process.

### 3.2 IMAP mailbox · input · **M**

The enum value `email_imap` already exists; implement it with
`aioimaplib`. Config: `host`, `port`, `username`, `password`
(write-only), `folder`, `poll_interval_sec`, `match` (`from`,
`subject_regex`), `extract` (regex named groups → context). Each
matching mail → `/v1/fire`-equivalent with `type` from config and
the extracted groups as context; mark seen or move to `processed`
folder. Idempotency key = `Message-ID`. Typical use: upstream vendors
that only email alerts.

### 3.3 Prometheus instant query · input · **S**

Not a new adapter: an `http_poll` **preset** that targets
`/api/v1/query?query=<PromQL>` and a JSONPath default of
`$.data.result[0].value[1]`. Lets a rule combine a PromQL scalar with
MQTT values without going through Alertmanager. Ship with 1.2.

### 3.4 SNMP traps · input · **M**, later

`pysnmp` trap receiver (UDP 162) → OID map → state values. Network
gear niche; do it when someone asks.

---

## 4. Tier 4 — platform

### 4.1 OIDC login for the admin UI · platform · **M–L**

**Why.** A public tool will be deployed in teams; local passwords do
not scale and auditors ask for SSO.

**Design.** `authlib` + the existing browser-session model
(`docs/AUTH_MODEL.md`). Settings: `KLOPOT_OIDC_ISSUER`, `CLIENT_ID`,
`CLIENT_SECRET`, `SCOPES`, `ADMIN_GROUP_CLAIM` / `ADMIN_GROUP_VALUE`.
Flow: `/v1/auth/oidc/login` → provider → `/v1/auth/oidc/callback`
creates or updates an `admin_users` row (`external_subject` column,
new migration) and issues the same session cookie as password login.
Role from the group claim; local password login stays as break-glass
when `KLOPOT_OIDC_LOCAL_LOGIN=true`. Test against a Dex container in
CI.

### 4.2 Generated SDKs · platform · **S**

From the committed `openapi/v1.json` (Phase 3 of the release plan):
`openapi-python-client` → `klopot-client` on PyPI,
`openapi-typescript` + a 40-line fetch wrapper → `@klopot/client` on
npm. Both generated in CI on tag, never hand-edited. Add a `fire()`
one-liner example to the README for each.

### 4.3 Grafana dashboard for `/v1/metrics` · platform · **S**

Ship `contrib/grafana/klopot.json`: fires per minute by severity,
suppressed by reason, delivery success rate per channel, breaker state
timeline, retry queue depth, engine tick latency, input freshness.
Link it from `DEPLOY.md` and the Observability section of the README.

### 4.4 Helm chart and Kubernetes manifests · platform · **M**

`charts/klopot` with the single-replica constraint enforced
(`replicaCount` fixed at 1 with a comment pointing at `DEPLOY.md`),
external MySQL by default, readiness on `/v1/health/ready`, secrets
via `existingSecret`. Publish to GHCR as an OCI chart alongside the
image.

### 4.5 Home Assistant add-on · platform · **M**, later

Repackaging of the image with HA's `config.yaml`, Ingress to `/admin`,
and the MQTT output (1.1) pre-wired to HA's broker. High reach in the
self-hosting community; only worth it after 1.1 and the demo path.

---

## 5. Cross-cutting work that makes every integration cheaper

- **External-event lifecycle (prerequisite for 1.3, 1.4 Pushover, 2.1,
  2.4).** Today a notification is a row and a delivery is a row; nothing
  links them to the outside world. Add, in one ADR and one migration:
  an **episode** (`episodes`: source kind, source identity such as
  Alertmanager fingerprint or rule id, opened/resolved/acked
  timestamps, stable `episode_key`); **provider references** on
  deliveries (`provider_message_id`, e.g. Telegram `(chat_id,
  message_id)`, Pushover `receipt`, PagerDuty `dedup_key`); an **inbox**
  for inbound events with provider-level dedup (`update_id`, receipt
  id, webhook delivery id); and **durable commands** (`lifecycle_commands`:
  acknowledge/resolve/cancel-retries, per channel, retried by the
  delivery worker) so an ack is applied exactly once even across a
  crash. `FireEnvelope.idempotency_key`, declared but unused in
  `dispatcher.py`, becomes the episode key's input.
- **Ack fan-out** is then a durable command per channel, not a
  best-effort `on_ack` hook.
- **Shared fire service**: extract the body of `POST /v1/fire` into
  `app/core/fire_service.py` so inputs (1.2, 3.2) and channel callbacks
  can fire without going through HTTP. Build with 1.2.
- **`intrusive` flag on channel kinds** in `meta_kinds.py`; the UI
  warns when an `info` template routes to an intrusive kind. Build
  with 1.4 (Pushover emergency) or 2.4.
- **Adapter test kit**: `tests/channels/_kit.py` with a fake `httpx`
  transport, a `Notification` factory and the standard assertions
  (idempotency key forwarded, secrets never logged, 5xx → `ok=False`).
  Every new adapter's test should be ~40 lines.

---

## 6. Suggested order and rough calendar

The first ordering served existing operators; this one favours new-user
acquisition, which is what a public launch needs. MQTT output moves
down only because the Home Assistant / IoT audience is a second market,
not the first.

| Step | Item | Effort | Why this order |
|------|------|--------|----------------|
| 0 | Working demo (`compose.demo.yml`, release plan Phase 5) | S | Nothing below matters if the first five minutes fail |
| 1 | 5 Shared fire service + 1.2 Alertmanager / Grafana receiver | M | Reaches people who already have alerts and need a better last mile |
| 2 | 4.3 Grafana dashboard | S | Makes operations inspectable on day one; pairs with step 1 |
| 3 | 1.1 MQTT output | S | Home Assistant / Node-RED loop; small and visible |
| 4 | 1.4 ntfy native | S | The self-hoster's phone channel; preset stays |
| 5 | 5 External-event lifecycle (episodes, provider refs, inbox, durable commands) | M | Foundation; nothing bidirectional before this |
| 6 | 1.3 Telegram actions | M | Most-felt daily improvement for operators |
| 7 | 1.4 Gotify, Pushover (emergency opt-in, receipts) | S + M | First intrusive channel, done safely |
| 8 | 2.1 PagerDuty | M | First "enterprise" ask, on the lifecycle foundation |
| 9 | 4.2 SDKs | S | Needs the OpenAPI drift check from the release plan |
| 10 | 2.2 Matrix, 2.3 Signal | S–M | Community asks |
| 11 | 3.1 Modbus | M | Origin domain, industrial reach |
| 12 | 2.4 Voice | M | Completes escalation |
| 13 | 4.1 OIDC | M–L | When the first team deployment appears |
| 14 | 3.2 IMAP, 4.4 Helm, 4.5 HA add-on, 2.5 WhatsApp, 3.4 SNMP, JSM Operations compat | — | Demand-driven |

Steps 0–4 are roughly two working weeks and are what the public
README's "works with" row should show on day one.
