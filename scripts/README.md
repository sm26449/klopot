# scripts/ index

## Install & operate

| Script | Purpose |
|--------|---------|
| `bootstrap.sh` | **Fresh install**: preflight (`.env`, Docker, the traefik network if configured) → `docker compose up -d --build` → wait healthy. Idempotent. |
| `deploy.sh` | **Upgrade a running install**: preflight → verified pre-deploy backup → rollback image tag → build → recreate → wait ready → compare schema/row counts. `--dry-run` prints the plan. |
| `backup.sh` | mysqldump + rotation. Runs inside the `backup` sidecar (`Dockerfile.backup`); can also be run by hand. |
| `restore_drill.sh` | **Prove backups restore**: throwaway MySQL, restore the newest dump, verify revision + row counts, optionally report via `POST /v1/fire`. Suited to a monthly host cron. |
| `admin.py` | Admin-account break-glass inside the container: `reset-password`, `unlock`, `list-sessions`, `revoke-sessions`. |
| `alertd_cli.py` | Config export / validate / import over the HTTP API (`ALERTD_URL` + `ALERTD_API_KEY` env). Run `python scripts/alertd_cli.py …`. |
| `seed.py` | **Bootstrap** seed, run automatically at container startup: `ui_default` / `banner_default` channels, default settings, bootstrap admin key and login. |

## Development

| Script | Purpose |
|--------|---------|
| `check.sh` | **Everything CI runs, locally**: ruff, mypy baseline, pytest (SQLite), node tests, OpenAPI drift; `--mysql` adds the MySQL gate on a throwaway container. |
| `dump_openapi.py` | Regenerate `openapi/v1.json` after a route or schema change (CI fails on drift). |
| `openapi_breaking.py` | Report breaking changes between two OpenAPI documents (used by CI). |
| `ui_smoke.mjs` | Browser smoke test of the admin UI (needs Playwright; see the header). |
| `generate_rules_doc.py` | Render a rules-pack YAML into a Markdown catalog of templates and rules. |

## Maintenance (upgrades of pre-1.0 databases)

Only for databases that were populated before 1.0.0 on a host whose MySQL ran
in a non-UTC timezone. Fresh installs never need these. See
[`docs/LEGACY_UTC.md`](../docs/LEGACY_UTC.md).

| Script | Purpose |
|--------|---------|
| `check_legacy_utc.py` | Read-only preflight: reports whether any historical timestamps need repair. |
| `correct_historical_utc.py` | Re-normalise `audit_log.ts` / `notifications_log.fired_at`. Dry-run by default; `--apply` writes once. |
| `correct_config_timestamps_b13.py` | Re-normalise config-row `created_at` / `updated_at`. Dry-run by default. |
| `scrub_audit_secrets.py` | Redact secret-bearing values from historical audit rows. |
