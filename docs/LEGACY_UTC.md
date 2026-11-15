# Legacy UTC repair (historical timestamps)

**Fresh installs are unaffected — skip this document.** It applies only when you
**upgrade a database that already held data** written by an older build, or move
such a database to a host in a different timezone.

alertd stores every timestamp as **naive UTC** at rest and serves it with a `Z`
suffix. Two classes of historical data predate that invariant and can carry a
wrong instant in a populated legacy database.

## Why legacy rows can be wrong

### 1. `audit_log.ts` and `notifications_log.fired_at` (migrations 0004 / 0005)

Before v1.4.1 these were written in **server-local** time. Migrations
[`0004`](../alembic/versions/20260517_1230_0004_audit_log_utc_migration.py) and
[`0005`](../alembic/versions/20260706_2030_0005_notifications_log_utc_migration.py)
normalise existing rows to UTC by subtracting **one** offset — the migration
host's current UTC offset. That is correct **only** for rows written in the same
DST season the migration runs in.

> A revision-0003 database with local-noon rows from both summer and winter,
> upgraded in winter (UTC+2), turns both into 10:00 UTC — but the summer row's
> true UTC is 09:00. The upgrade succeeds and silently keeps the wrong instant.

These migrations are **published and forward-only**: their effect is *not*
changed. The per-row, DST-correct repair is applied **after** upgrade by a
reviewed tool, not by rewriting the migration.

### 2. Config-row `created_at` / `updated_at` (session timezone, B-13)

A MySQL container may run with a local `TZ` (e.g. `Europe/Bucharest`) so that
quiet hours read local wall time. Before the session-UTC fix, the DB session inherited that zone,
so every `CURRENT_TIMESTAMP` server default (`created_at` / `updated_at` across
the config tables) stored the **local** wall clock and then served it with a `Z`
suffix — misdated by the offset. New writes are UTC; rows written **before** the
fix deployed need repair.

## Affected deployments

- A **populated** database upgraded across these versions.
- Historical rows spanning **more than one DST season** (the single-offset
  migrations mis-shift the off-season ones).
- A database **moved to a host in a different timezone** than the one that wrote
  the rows.

A fresh install, or a database whose history lies entirely in one DST season
(the original home deployment), needs no change — the preflight below confirms
this and reports zero suspect rows.

## Procedure

### Step 1 — preflight (read-only, writes nothing)

```bash
docker compose exec alertd python -m scripts.check_legacy_utc \
    --config-cutoff <SESSION-UTC-DEPLOY-INSTANT-UTC-ISO>
```

It reports, per domain, whether a correction marker already exists and how many
rows a repair would change, and exits `2` when action is needed (`0` otherwise).
Its dry-run uses the repair tools' own logic, so its count matches an apply. Omit
`--config-cutoff` to assess only the log domain (0004/0005).

> `--config-cutoff` is the instant the **session-UTC fix** (B-13) was deployed:
> rows at or after it are already UTC and must not be shifted.

### Step 2 — repair (dry-run first, then `--apply`)

Log domain (0004/0005), DST-correct per row:

```bash
docker compose exec alertd python -m scripts.correct_historical_utc           # dry run
docker compose exec alertd python -m scripts.correct_historical_utc --apply
```

Config domain (B-13), bounded by the deploy cutoff:

```bash
docker compose exec alertd python -m scripts.correct_config_timestamps_b13 \
    --cutoff <SESSION-UTC-DEPLOY-INSTANT>                                       # dry run
docker compose exec alertd python -m scripts.correct_config_timestamps_b13 \
    --cutoff <SESSION-UTC-DEPLOY-INSTANT> --apply
```

Each repair converts every row with the zone's **historical** offset for that
row's own instant (summer −3h, winter −2h for Europe/Bucharest in one run) and
writes an `audit_log` marker so it **cannot be applied twice**. The already-UTC
log fields are never touched by the config tool, and post-cutoff UTC rows are
never touched by either. Re-running on already-correct data is a no-op and still
records the marker, which silences the preflight for that domain.

### Timezone / provenance

Both tools default the source zone to `settings.timezone`. If the current data
was written under a **different** zone (a moved database), pass `--timezone` (and,
for the log tool, `--applied-offset` when the migration itself ran off-season or
on another host). Establish the provenance before applying.
