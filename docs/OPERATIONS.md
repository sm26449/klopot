# Operational monitoring

The admin **Operations / Monitorizare** page (`/admin/#/operations`) and
`GET /v1/operations` expose the same read-only snapshot. The API requires
`read` scope. It includes delivery, local action and provider-update queue
states, worker liveness, configured Telegram receivers, used MQTT connections,
and up to 20 recent terminal failures linked to their notifications.
Credentials, frozen destination configs, raw callbacks and action tokens are
never returned. The page refreshes every ten seconds and marks stale data if
a refresh fails.

## Reading queue state

- **Pending** includes scheduled backoff and active leases; a nonzero count
  alone does not mean an outage.
- **Overdue** means the next attempt is more than 120 seconds late, with no
  active delivery lease. The overdue age measures lateness from the scheduled
  attempt; oldest pending measures row age from creation.
- **Failed** is the retained inventory of terminal failures. It is not a
  recent failure rate and remains nonzero until normal retention removes the
  owning notification. Inspect the related log and audit for context.
- Applying a Telegram action and editing its provider keyboard use separate
  queues. A failed provider edit does not undo a successful local ACK/snooze.

## Prometheus and Grafana

Scrape `/v1/metrics`. Production requires a read-scoped API key in `X-API-Key`
unless explicitly configured otherwise. Keep the key in a mounted secret,
separate from Git and dashboard JSON. A sample scrape configuration is in
[`contrib/prometheus/scrape.example.yml`](../contrib/prometheus/scrape.example.yml).

Import [`contrib/grafana/klopot.json`](../contrib/grafana/klopot.json) through
Grafana's dashboard import and select the Prometheus datasource. Job and
instance selectors scope every panel. The 16 panels cover queues/age, terminal
failures, workers, delivery success, breakers, Telegram/MQTT, engine tick age
and latency, input age and alert rates.

[`contrib/prometheus/klopot.rules.yml`](../contrib/prometheus/klopot.rules.yml)
contains eight optional alert rules. Load them into your Prometheus rule files
and route notifications through a service independent of Klopot: Klopot
cannot report its own complete outage through itself. `KlopotUnavailable`
assumes the sample job name `klopot`; adjust it for another job name.

| Metric | Meaning |
|--------|---------|
| `alertd_operations_collection_success` | Last scrape could collect operational DB state. Check before trusting queue values. |
| `alertd_queue_rows{queue,state}` | Retained row count in deliveries/actions/provider queues. |
| `alertd_queue_overdue{queue}` | Pending rows more than 120s late; leased deliveries excluded. |
| `alertd_queue_oldest_pending_seconds{queue}` | Oldest pending row age, including future retries. |
| `alertd_queue_oldest_overdue_seconds{queue}` | Oldest overdue attempt lateness. |
| `alertd_worker_up{worker}` | Background task exists and is still running (`engine`, `delivery`, `scheduler`, `telegram`, `lifecycle` — Pushover receipt cancel/poll). |
| `alertd_engine_last_tick_timestamp` | Last successful engine evaluation cycle; detects an alive but stuck task. |
| `alertd_engine_tick_duration_seconds` | Histogram of engine cycle duration. |
| `alertd_dispatch_attempts_total{channel,outcome}` | Completed attempts: ok/failed; excludes scheduling deferrals. |
| `alertd_channel_commands_total{queue,state}` | Committed terminal action/provider outcomes in this process. |
| `alertd_telegram_receiver_connected{channel}` | Receiver alive, with a successful poll and no current polling error. |
| `alertd_telegram_last_poll_timestamp{channel}` | Last successful poll; zero before first success. |
| `alertd_mqtt_output_active{channel}` | Enabled output has been used in this process. |
| `alertd_mqtt_output_connected{channel}` | Live persistent output connection. Unused channels are not outages. |
| `alertd_api_key_rate_limited_total{key}` | Requests refused (`429`) because the key was over its own `rate_limit_per_min` ([AUTH_MODEL](AUTH_MODEL.md#rate-limit)). A steady rise: the caller's limit is too low, or the key is being misused. |

Also exported: `alertd_fires_total`, `alertd_escalations_total`,
`alertd_rule_eval_duration_ms`, `alertd_rule_eval_errors_total`,
`alertd_dispatch_latency_ms`, `alertd_dispatch_failures_total`,
`alertd_channel_breaker_state`, `alertd_input_msg_lag_sec`,
`alertd_input_connected`, `alertd_log_table_rows`, `alertd_aggregate_overflow`,
`alertd_retention_runs_total`, `alertd_retention_rows_deleted_total`,
`alertd_retention_last_run_timestamp` and `klopot_activity_dropped_total`
(activity-log rows dropped because the writer queue was full —
[ACTIVITY_LOG.md](ACTIVITY_LOG.md)). Help texts are in `app/metrics.py`.

Counters reset on restart; use `rate` / `increase`. Queue gauges come from the
database and survive restarts. Connection labels disappear when a channel is
disabled or removed. MQTT availability reports broker connectivity; its
heartbeat carries the engine tick timestamp separately. No availability
message proves that the evaluator is healthy by itself.

## Kurier watchdog

Klopot cannot report its own outage through itself. With a `kurier` SMS
channel ([Kurier](https://github.com/sm26449/kurier), the SMS gateway) whose
**Watchdog** is on, Kurier does it ([ADR-0003](adr/0003-kurier-watchdog.md);
the contract is Kurier's ADR-0001, Kurier 1.15+):

- Every 60 s Klopot pings `POST {kurier_url}/api/watchdogs/klopot-<channel>/ping`
  (a channel name too long for Kurier's 64 characters is cut and ends in a
  hash of the whole name, so two channels never share a watchdog) with `status: ok`, or `fail` and the reason when an essential component is
  down — the database, the delivery worker, the rule engine — or the engine
  is stuck (`engine_stalled`), or the outbox is not draining. The ping runs in
  its own task, never in the rule engine.
- Kurier sends an SMS when the pings stop for `watchdog_timeout_sec` (default
  180 — a deploy's restart fits in it) or say `fail`, and one when Klopot is
  back. Recipients: `watchdog_to`, else Kurier's `SMS_WATCHDOG_TO`, else its
  `SMS_DEFAULT_RECIPIENTS`. It works over LTE, so it also covers an internet
  outage.
- The answer carries Kurier's modem state. Klopot raises
  `kurier_unreachable` after three failed pings in a row (the error says why:
  `HTTP 401` wrong key, `HTTP 422` a bad setting, `HTTP 404` a Kurier without
  watchdogs, or a `200` that is not Kurier's JSON) and `kurier_modem_down`
  when the modem reports `registered: false` — or when Kurier has not reached
  the router for three minutes. The modem episode closes only on
  `registered: true`; an answer without the modem state changes nothing. Both are episodes
  with a recovery (`kurier_reachable`, `kurier_modem_up`), in the built-in
  self-monitoring templates, routed to `ui_default` on install. **Route them
  to Telegram or push too** — not only to SMS, the path they report broken.
- Klopot does not unregister when it stops: a stopped Klopot should alert. To
  silence it on purpose (maintenance), turn the watchdog off on the channel
  and `DELETE {kurier_url}/api/watchdogs/klopot-<channel>`.
- Not covered: the host itself going down takes Klopot and Kurier with it —
  that needs a watcher outside the host.
