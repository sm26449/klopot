# Documentation index

The living documents, and what each one answers. Romanian translations
(`*.ro.md`) sit next to their originals.

## Start here

Working on the code? The developer commands (tests, lint, deploy) and a
layout of the code are in the repository-root `CONTRIBUTING.md`;
`scripts/README.md` indexes the scripts.

| Document | Answers |
|----------|---------|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | What has shipped, how a deployment is verified, and what remains? |
| [GETTING_STARTED.md](GETTING_STARTED.md) | How do I run alertd and fire my first alert, end to end? |
| [ARCHITECTURE.md](ARCHITECTURE.md) | What are the components, how does data flow, what is the schema? |
| [API.md](API.md) | What is the REST + WebSocket surface, auth, error model? (live truth: `/openapi.json`) |
| [EXPRESSION_LANGUAGE.md](EXPRESSION_LANGUAGE.md) | What can a rule condition say, and which helpers exist? Template placeholders and filters |
| [PACKS.md](PACKS.md) | How do I install a ready-made set of rules, write my own pack with parameters, or export part of my config as a pack? |
| [INCIDENTS.md](INCIDENTS.md) | How do active problems, acknowledgement, hysteresis and recovery notifications work? |
| [WEB_PUSH.md](WEB_PUSH.md) | How do phones and computers get alerts as notifications without an app (installable admin UI, iPhone Home Screen), and what are the limits? |
| [ACTIVITY_LOG.md](ACTIVITY_LOG.md) | What reached Klopot and what it sent: requests, delivery attempts, events, and the rules that decide what is kept |
| [TELEGRAM.md](TELEGRAM.md) | How do I create a dedicated bot and enable acknowledgement / snooze buttons? (Romanian) |
| [MQTT_OUTPUT.md](MQTT_OUTPUT.md) | How do MQTT output, QoS, replay IDs, availability and heartbeat work? |
| [OPERATIONS.md](OPERATIONS.md) | How do I inspect queues/workers, scrape metrics and import the Grafana dashboard? |
| [ADMIN_UI.md](ADMIN_UI.md) | What does each admin screen do, which API does it use, and which UI conventions and test rules must a change keep? |

## Reference

| Document | Answers |
|----------|---------|
| [SCHEMA.md](SCHEMA.md) | What do the tables and columns mean? |
| [AUTH_MODEL.md](AUTH_MODEL.md) | How do API keys and admin-UI sessions work? |
| [EXTENSIBILITY.md](EXTENSIBILITY.md) | How do I add a channel, input or rule helper? |
| [LEGACY_UTC.md](LEGACY_UTC.md) | Which historical timestamps were stored in local time, and what is the policy for them? |
| [EDGE_CASES.md](EDGE_CASES.md) | Which tricky behaviours are deliberate, and why? |
| [NFR.md](NFR.md) | What are the non-functional requirements and budgets? |

## Operations

| Document | Answers |
|----------|---------|
| [DEPLOY.md](DEPLOY.md) | How is alertd deployed, migrated, backed up and rolled back? (upgrade = `scripts/deploy.sh`) |
| [RELEASING.md](RELEASING.md) | When is there a release, what is a release candidate, and which commands make one? (`scripts/version.py`) |

## Project

| Document | Answers |
|----------|---------|
| [INTEGRATIONS_ROADMAP.md](INTEGRATIONS_ROADMAP.md) | Which channels / inputs / platform pieces are designed and prioritised? |

## Subdirectories

| Directory | Contents |
|-----------|----------|
| [adr/](adr/) | Architecture Decision Records (ADR-0001 fixes the Klopot name, logo and colour tokens; ADR-0002 the optional OS-native theme families; ADR-0003 Kurier watching Klopot; ADR-0004 history functions in rule expressions; ADR-0005 parametric rules). |
| [brand/](brand/) | Identity assets — marks, favicon, colour concepts. |

