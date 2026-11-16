// Curated "what's new" shown from the sidebar version click. Newest first; keep
// a handful of highlights — the full history lives in CHANGELOG.md at the repo
// root. English only (release notes are not translated per-line).
export const CHANGELOG = [
  {
    version: "1.2.0",
    items: [
      "Ready for the internet: the traefik overlay is private by default, and compose.public.yml opens only POST /v1/fire — read the upgrade notes.",
      "API keys: limit a key to addresses (\"Add my address\") and to a number of requests per minute.",
      "Inbound inputs need a token of at least 32 characters by default; the Inputs page marks a missing or short one. Each input can limit its own requests.",
      "Wrong keys, wrong input tokens and failed sign-ins are budgeted per address; a remote guesser can no longer lock you out of the admin.",
      "Anonymous health checks get the status only; ALERTD_ADMIN_ALLOW_CIDRS keeps the admin to your networks.",
    ],
  },
  {
    version: "1.1.1",
    items: [
      "No default passwords: the database URL and MySQL passwords must be set, and escalation is off until you name a channel — read the upgrade notes.",
      "Telegram (self-hosted Bot API server), Pushover and Twilio take an api_url; timeouts and the snooze-until-morning hour are settings.",
      "The template preview prints numbers and accepts icons exactly as the server does.",
      "A list that fails to load says so instead of looking empty; pickers and search load every item.",
      "Phone layout: list tables become one card per row.",
    ],
  },
  {
    version: "1.1.0",
    items: [
      "Alertmanager / Grafana receiver, and native ntfy, Gotify and Pushover channels (Pushover emergency cancelled on acknowledgement).",
      "Web Push: install the admin UI as an app and get alerts on phones and desktops, with per-device minimum severity and pause.",
      "Activity log: every request, provider attempt and state change, with editable keep / ignore rules.",
      "Configuration packs, a setup guide, SMS providers (http, Twilio, Teltonika) and Python / TypeScript client libraries.",
      "Hardening from two pre-release reviews — read the upgrade notes in CHANGELOG.md before upgrading.",
    ],
  },
  {
    version: "1.0.1",
    items: [
      "Operational monitoring: persistent queues, worker state, Telegram/MQTT connectivity, recent failures, Prometheus metrics and a portable Grafana dashboard.",
      "MQTT output with persistent connections, reconnect, QoS, JSON templates, stable delivery identity, availability and engine heartbeat.",
      "Opt-in rule incidents with acknowledgement, hysteresis and recovery notifications.",
      "Dedicated Telegram bot buttons for acknowledgement and snooze, with durable action processing and audit.",
      "Durable escalation retries and per-channel delivery details.",
    ],
  },
  {
    version: "1.0.0",
    items: [
      "First public release of Klopot.",
      "Admin UI in English and Romanian, with the Klopot theme and optional OS-native theme families.",
      "Per-kind help panels in the Channels, Inputs, Variables, Rules and Templates editors.",
      "Three deployment variants: production, behind traefik, and development.",
    ],
  },
];
