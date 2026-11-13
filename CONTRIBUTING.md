# Contributing to Klopot

Thanks for picking this up. The project is small and opinionated;
this doc covers the pieces a new contributor needs to keep the
code coherent.

## Dev setup

```bash
git clone git@github.com:sm26449/klopot.git
cd klopot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

> **Use a virtualenv.** A dependency (`http-ece`, for Web Push) needs to
> build against the venv's Python; the system Python may lack the headers
> and fail the install. All the commands below assume the venv is active;
> without activating it, prefix them (e.g. `.venv/bin/python -m pytest`).
>
> **One command for everything CI runs:** `scripts/check.sh` (add `--mysql`
> to also run the MySQL gate against a throwaway container).

The admin-UI tests also need Node (`node --test tests/js/*.mjs`); the
accessibility suite installs its dev tooling with `npm install`.

Then either run the development stack (alertd + MySQL + a local MQTT
broker, built from your checkout):

```bash
docker compose -f docker-compose.yml -f compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f compose.dev.yml logs -f alertd
```

…or just the DB and broker, and run alertd from source for fast iteration:

```bash
docker compose -f docker-compose.yml -f compose.dev.yml up -d mysql mosquitto
alembic upgrade head
ALERTD_BOOTSTRAP_ADMIN_KEY=alertd_dev_key \
ALERTD_DATABASE_URL=mysql+aiomysql://alertd:alertd@localhost:3306/alertd \
uvicorn app.main:app --reload
```

## Project layout

```
app/
  main.py             FastAPI factory, lifespan, middleware
  config.py           Pydantic Settings (ALERTD_ env prefix)
  metrics.py          Prometheus collectors (Counter / Histogram / Gauge)
  logging_setup.py    JSON / console formatters + trace_id contextvar
  api/v1/             HTTP layer; one module per resource
  schemas/            Pydantic request/response models
  services/           Config import/export
  utils/              safe_http + egress (SSRF-safe outbound), cron, time, redaction
  admin_ui/static/    Build-less admin SPA (Preact): views/, lib/, i18n/
  core/               Engine, eval, dispatcher, outbox + delivery worker, gating, rendering, retention
  channels/           Outbound adapters (ui, telegram, sms, email, push, webhook)
  inputs/             Inbound adapters (mqtt, webhook, http_poll, sms_inbox)
  db/                 SQLAlchemy 2.0 async, models, session factory
docs/                 ARCHITECTURE, DEPLOY, API, ADRs, etc. (index: docs/README.md)
scripts/              check.sh, deploy.sh, bootstrap.sh, alertd_cli, backup.sh (index: scripts/README.md)
alembic/              Schema migrations
.github/workflows/    CI
```

Read `docs/ARCHITECTURE.md` first; it diagrams the engine /
dispatcher / channel manager wiring.

## Coding conventions

### Style

- Type hints required on every function signature.
- Use `from __future__ import annotations` so modern syntax
  (`str | None`, `list[int]`) works on Python 3.12+ uniformly.
- Default to no comments; only add a comment when the *why* is
  non-obvious (subtle invariant, workaround for a specific bug).
- Don't add error handling for things that can't fail. Trust
  framework guarantees; validate at system boundaries only.

### Lint

```bash
ruff check app scripts          # style + import sort + simple bugs
ruff format app scripts         # formatter (replaces black)
mypy app > mypy-report.txt; mypy-baseline filter < mypy-report.txt
```

CI runs `ruff check` and the mypy baseline gate: `mypy-baseline.txt` holds
the accepted pre-existing errors, and a PR fails only on **new** ones.

### Tests

```bash
pytest                          # full suite
pytest tests/core/              # narrow to a directory
pytest -k engine                # filter by name
pytest --cov=app --cov-report=term-missing
node --test tests/js/*.mjs      # admin-UI tests (after `npm ci`)
```

The default run uses in-memory SQLite. Tests marked `mysql` need a real
MySQL (locking, upserts) and tests marked `sqlite` depend on the SQLite
harness; CI runs both gates. Locally: `scripts/check.sh --mysql`, or point
`ALERTD_TEST_DATABASE_URL` at a disposable MySQL and run
`pytest -m "not sqlite"`. After changing a route or schema, regenerate the
spec with `python scripts/dump_openapi.py` and commit `openapi/v1.json`.

Test layout follows source: `tests/core/test_engine.py` exercises
`app/core/engine.py`. Async tests use `pytest-asyncio`. The S12c
roadmap calls for ≥80% coverage on `app/core/` + `app/channels/`.

## Design decisions (ADRs)

Significant or hard-to-reverse decisions are recorded as Architecture
Decision Records in [`docs/adr/`](docs/adr/). To propose one:

1. Copy the format of an existing ADR; number it sequentially.
2. State the context, the decision, and the consequences — including
   what it rules out.
3. Open it in a PR and link it from the code or doc it governs.

Don't silently contradict an accepted ADR; supersede it with a new one.

**Colour-token rule (ADR-0001).** The admin UI's palette is fixed by
[`docs/adr/0001-brand-identity-klopot.md`](docs/adr/0001-brand-identity-klopot.md):
indigo `--accent` is interaction, amber `--signal` is live indicators
only, and green/amber/red are semantic only. **A new colour literal in
`app/admin_ui/static/` is a defect** — add or reuse a CSS token, and if a
genuinely new colour is needed, add it to the palette in a new ADR first.
`tests/js/contrast.test.mjs` enforces the tokens' AA contrast.

## Commits

Conventional Commits format —
[spec](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <short imperative>

<longer body if needed — what changed and why>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`,
`build`, `ci`, `perf`. Scope is optional; use one when narrowing
to a subsystem (`s10b`, `dispatcher`, `mqtt`, etc.).

Don't reference AI assistants or tools in commit messages, and add **no
trailers** of any kind (no `Co-Authored-By`, no session links). This
overrides any attribution footer a tool suggests.

## Pull requests

- Keep PRs small and reviewable. One concern per PR.
- Include the *why* in the PR body, not just the *what* — diffs
  show the *what*.
- If the change touches a config key or schema, update the
  relevant doc in the same PR (`docs/SCHEMA.md`,
  `docs/DEPLOY.md`, `.env.example`).
- CI must pass. Smoke + lint are gating today; tests join the
  gate after S12c.

## Releasing

1. Bump version in `pyproject.toml` and `app/__init__.py`.
2. Update `CHANGELOG.md` with the new heading.
3. `git tag vX.Y.Z && git push --tags`.
4. Verify `/v1/health` reports the new version after redeploy.

## License

Licensed under the **Apache License 2.0** — see [`LICENSE`](LICENSE) and
[`NOTICE`](NOTICE). By contributing you agree that your contributions are
licensed under the same terms. Contributions are welcome; please read the
[Code of Conduct](CODE_OF_CONDUCT.md) first, and report security issues
privately per [`SECURITY.md`](SECURITY.md).
