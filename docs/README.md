# Documentation index

The living documents, and what each one answers. Romanian translations
(`*.ro.md`) sit next to their originals.

## Start here

Working on the code? The developer commands (tests, lint, deploy) and a
layout of the code are in the repository-root `CONTRIBUTING.md`;
`scripts/README.md` indexes the scripts.

| Document | Answers |
|----------|---------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | How do I run alertd and fire my first alert, end to end? |
| [ARCHITECTURE.md](ARCHITECTURE.md) | What are the components, how does data flow, what is the schema? |
| [API.md](API.md) | What is the REST + WebSocket surface, auth, error model? (live truth: `/openapi.json`) |
| [EXPRESSION_LANGUAGE.md](EXPRESSION_LANGUAGE.md) | What can a rule condition say, and which helpers exist? |

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

## Project

| Document | Answers |
|----------|---------|
| [INTEGRATIONS_ROADMAP.md](INTEGRATIONS_ROADMAP.md) | Which channels / inputs / platform pieces are designed and prioritised? |

## Subdirectories

| Directory | Contents |
|-----------|----------|
| [adr/](adr/) | Architecture Decision Records (ADR-0001 fixes the Klopot name, logo and colour tokens). |
| [brand/](brand/) | Identity assets — marks, favicon, colour concepts. |

