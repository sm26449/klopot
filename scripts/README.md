# scripts/ index

## Install & operate

| Script | Purpose |
|--------|---------|
| `bootstrap.sh` | **Fresh install**: preflight (`.env`, Docker, the traefik network if configured) → `docker compose up -d --build` → wait healthy. Idempotent. |
| `deploy.sh` | **Upgrade a running install**: preflight → verified pre-deploy backup → rollback image tag → build → recreate → wait ready → compare schema/row counts. `--dry-run` prints the plan; `--runtime-dir=DIR` when `.env`/compose live outside the checkout. |
| `backup.sh` | mysqldump + rotation. Runs inside the `backup` sidecar (`Dockerfile.backup`); can also be run by hand. A failed or incomplete dump exits non-zero and leaves no file. |
| `backup_scheduler.sh` | The backup sidecar's entrypoint: runs `backup.sh` per `BACKUP_CRON` (minute/hour as `*`, `N` or `*/N`). POSIX sh. |
| `restore_drill.sh` | **Prove backups restore**: throwaway MySQL, restore the newest dump, verify revision + row counts, optionally report via `POST /v1/fire`. Suited to a monthly host cron. |
| `version.py` | **The version in every file** (`app/__init__.py`, `pyproject.toml`, the SDKs): `set 1.3.0-rc.1` writes it (PEP 440 form for the Python packages), `check` compares them, `tag` / `prerelease` for CI. See `docs/RELEASING.md`. |
| `_klopot_url.sh` | Sourced by the three scripts above: `klopot_url` = `$ALERTD_URL`, else `127.0.0.1` on `KLOPOT_HTTP_PORT` from `.env` (default 5090). |
| `admin.py` | Admin-account break-glass inside the container: `reset-password`, `unlock`, `list-sessions`, `revoke-sessions`. |
| `telegram_setup.py` | Discover chat and user IDs for a dedicated bot before enabling polling; run `python -m scripts.telegram_setup`. See `docs/TELEGRAM.md`. |
| `alertd_cli.py` | Config export / validate / import over the HTTP API (`ALERTD_URL` + `ALERTD_API_KEY` env). Run `python scripts/alertd_cli.py …`. |
| `seed.py` | **Bootstrap** seed, run automatically at container startup: `ui_default` / `banner_default` channels, default settings, bootstrap admin key and login. |

## Development

| Script | Purpose |
|--------|---------|
| `check.sh` | **Everything CI runs, locally**: ruff, mypy baseline, pytest (SQLite), node tests, OpenAPI + SDK drift, gitleaks; `--mysql` adds the MySQL gate on a throwaway container, `--e2e` the browser tests. |
| `e2e.sh` | **Browser end-to-end tests** (`tests/e2e/*.e2e.mjs`, Playwright): builds the image, starts a throwaway fresh install (MySQL 8 + app on a free port), runs first login, every page in EN + RO, a phone viewport and the editors. `--no-build`, `--keep`, `E2E_ONLY=<substring>`. |
| `rules_sim.sh` + `rules_sim.py` | **Rule engine end to end over MQTT**: a throwaway install + Mosquitto; imports an input, variables, templates and rules, publishes messages in phases and checks every rule's outcome through the API (fires, no_data, stale, computed/aggregate, incidents, inhibition, auto-disable, rendering, write-time checks). `--no-build`, `--keep`, `SIM_ONLY=<substring>`. |
| `screenshots.sh` | README screenshots (`docs/screenshots/`) from synthetic data: a throwaway install through `e2e.sh` (`E2E_ONLY=none`, `E2E_AFTER`), a local HTTP sink, `screenshots.mjs` seeds a demo site and shoots the admin UI. |
| `vapid_keys.py` | Print a VAPID key pair for the Web Push channel; the private key goes into `secrets.env` as `KLOPOT_SECRET_VAPID_PRIVATE` (docs/WEB_PUSH.md). |
| `render_icons.mjs` | Re-render the installable-app icons (`app/admin_ui/static/icons/*.png`) from the brand mark; `node scripts/render_icons.mjs` after `npm ci`. |
| `dump_openapi.py` | Regenerate `openapi/v1.json` after a route or schema change (CI fails on drift). |
| `generate_sdks.sh` | Regenerate the client SDKs in `sdk/` from `openapi/v1.json` (run right after `dump_openapi.py`; needs `npm ci`). `--check` fails on drift — `check.sh` runs it. See `sdk/README.md`. |
| `openapi_breaking.py` | Report breaking changes between two OpenAPI documents (used by CI). |
| `ui_smoke.mjs` | Quick browser smoke test against any running instance (Playwright; see the header). For the full suite use `e2e.sh`. |
| `generate_rules_doc.py` | Render an exported config / rules YAML into a Markdown catalog of templates and rules (`--input`, `--output`). |

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
