# MQTT output

Create a channel with `kind: mqtt`, then route a template to it. MQTT input
connections and subscriptions remain independent. The output owns a persistent
connection, opens it on its first send, reconnects with backoff, and closes it
on service shutdown. A broker outage returns a failed attempt to the normal
durable outbox; the adapter does not introduce a second notification retry loop.

```json
{
  "name": "mqtt_notifications",
  "kind": "mqtt",
  "config": {
    "topic_template": "klopot/notifications/{type}",
    "qos": 1,
    "retain": false,
    "host": "mosquitto",
    "port": 1883,
    "username_ref": "ALERTD_MQTT_USERNAME",
    "password_ref": "ALERTD_MQTT_PASSWORD",
    "instance_id": "home",
    "tls": false
  }
}
```

Omit host/port/instance_id to use `ALERTD_MQTT_HOST`, `ALERTD_MQTT_PORT` and
`ALERTD_MQTT_CLIENT_ID`. Omitted credentials use the corresponding MQTT env
references. References are subject to the existing secret allowlist. Explicit
literal credentials are write-only and masked on read/export/audit. Broker
defaults are frozen when the delivery is enqueued; retries retain their
destination. An environment credential reference still resolves its current
value, allowing rotation like other adapters.

`tls: true` enables TLS with system CA and hostname verification; typically
configure port 8883 for such a broker. Insecure TLS is not offered. The
connection identifier is generated independently from input client IDs.

## Payload and replay identity

Default messages are JSON objects with notification fields (`id`, `type`,
`severity`, `title`, `message`, `fired_at`, `rule_id`, `incident_id`, `icon`,
`vars_payload`) and **`delivery_id`**, the stable outbox transport key. UTC
timestamps carry `Z` (or an explicit offset). Repeated delivery attempts carry
the same delivery_id; consumers must deduplicate it. MQTT QoS 1/2 alone cannot
deduplicate a new publish created by an outbox retry after an ambiguous failure.

`topic_template` accepts `{type}`, `{severity}`, `{id}`, `{instance}` and
`{channel}`. A rendered topic must be nonempty, at most 65535 UTF-8 bytes, and
contain no `+`, `#` or NUL. Validate both configured and rendered values.
Notification payloads are limited to 256 KiB. `timeout_sec` (default 10, range
1–20) bounds the send wait; the manager also enforces its normal attempt ceiling.

Optional `payload_template` must render a JSON object, using the standard
renderer and `| jsonstr` filter for embedded text:

```json
{"text":"{title | jsonstr}: {message | jsonstr}","severity":"{severity}"}
```

The adapter always inserts the real delivery_id after rendering, even if the
template tries to override it. Retain is **off** by default: retained alerts
would otherwise replay to newly connected subscribers. Enabling it is an
operator choice, independent from QoS.

## Availability and heartbeat

The defaults, scoped by instance and channel, are:

- `klopot/{instance}/outputs/{channel}/status`: retained `online`; retained
  LWT `offline` on connection loss, and explicit `offline` on graceful close.
- `klopot/{instance}/outputs/{channel}/heartbeat`: non-retained JSON every
  30 seconds, with `timestamp` and `engine_last_tick_timestamp`. A zero engine
  timestamp means no successful tick since boot. A stale engine timestamp
  indicates evaluator trouble even when the MQTT connection is healthy.

Set `availability_topic` or `heartbeat_topic` to empty text to disable that
feature. These two templates support only instance/channel placeholders.
Choose a distinct instance_id per installation and avoid sharing custom status
topics across output channels. Editing destination config retires the old
connection before opening its replacement. The cache is bounded to 32 active
output configurations; least recently used connections close on eviction.

The **Operations** page shows connection state without network probes.
`GET /v1/channels/{id}/health` performs a short separate broker connection test
without publishing a notification or availability message. Migration `0027`
adds the output enum without changing any existing channel or route.
