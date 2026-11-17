# Releasing

How a Klopot version gets from `main` to a release: when there is one,
the release candidate before every final, and the commands.

## Policy

- **Between releases, `main` only gets commits and pushes.** A change waits
  for the next release; there is no release per change.
- **A release cycle starts with a release candidate**, `X.Y.Z-rc.1`, on a
  planned day, when `main` has something worth releasing — at most once a
  week, usually every two to four. No changes worth it, no cycle.
- **The candidate runs in production first.** It is deployed to the
  maintainers' own instance and watched for about a week.
- **From rc.1 on, the release only takes fixes** for what the candidate
  showed — never a new feature; that waits for the next cycle. A fix makes
  `rc.2`, which starts the week again.
- **The final is the last candidate, renamed.** Same code; only the version
  changes. A code change after the last candidate is another candidate.
- **An urgent fix** (security, data loss, a broken install) can be a patch
  release `X.Y.Z+1` straight away, with or without a candidate — say why in
  its changelog entry.
- If a cycle needs more than three candidates, stop and ask why before rc.4.
- **Reopening a cycle for a feature** is an exception the owner decides
  explicitly, never a default: the next candidate carries the feature, the
  week in production restarts from it, and the release notes say so. Used
  once: 1.3.0-rc.3 (Kurier watchdog, ADR-0003), decided 2026-11-17.

The public sees finals: the GitHub release marked *Latest*, the image
`:latest`, the README and klopot.dev. A candidate is a GitHub **pre-release**
and the image `:vX.Y.Z-rc.N` only.

## Versions

| Where | Final | Candidate |
|-------|-------|-----------|
| git tag, image tag | `v1.3.0` | `v1.3.0-rc.1` |
| `app.__version__`, `/v1/version`, admin UI, TypeScript SDK | `1.3.0` | `1.3.0-rc.1` |
| `pyproject.toml`, Python SDK (PEP 440, what pip shows) | `1.3.0` | `1.3.0rc1` |

`scripts/version.py` writes all of them and checks they agree (a test does
too, and CI refuses to publish a tag that differs from it):

```bash
scripts/version.py                  # 1.3.0-rc.1
scripts/version.py set 1.3.0-rc.1   # every file, each in its form
scripts/version.py check
```

Only `X.Y.Z` and `X.Y.Z-rc.N` exist — no alpha / beta.

## Changelog

Entries collect under `## [Unreleased]` through the whole cycle, candidates
included; the section gets its version and date at the final. A candidate's
notes are its GitHub pre-release text: what is new since the last final, and
for `rc.2`+ what changed since the previous candidate. The admin UI's
"what's new" (`app/admin_ui/static/changelog.js`), the README status lines,
`docs/PROJECT_STATUS.md` and klopot.dev change at the final only.

## A release candidate

```bash
scripts/check.sh --mysql && scripts/e2e.sh          # the full gate
scripts/version.py set 1.3.0-rc.1
.venv/bin/python scripts/dump_openapi.py && scripts/generate_sdks.sh
scripts/check.sh --fast
git commit -am "chore(release): 1.3.0-rc.1"
git tag -a v1.3.0-rc.1 -m "Klopot 1.3.0-rc.1"
git push && git push origin v1.3.0-rc.1            # CI publishes :v1.3.0-rc.1
gh release create v1.3.0-rc.1 --prerelease --title "Klopot 1.3.0-rc.1" --notes-file <notes>
scripts/deploy.sh 1.3.0-rc.1 --dry-run              # then without --dry-run
```

While a candidate is out, `main` stays open. If a feature lands there before
the final, fixes for the candidate go on a `release/X.Y` branch cut at the
candidate's tag (and are merged back to `main`); the next candidate and the
final are tagged on that branch. Without such a feature, everything stays on
`main`.

## The final

After a week of the last candidate in production with nothing to fix:

```bash
scripts/version.py set 1.3.0
.venv/bin/python scripts/dump_openapi.py && scripts/generate_sdks.sh
# CHANGELOG: [Unreleased] → [1.3.0] — <date>; changelog.js, README, PROJECT_STATUS
scripts/check.sh --fast
git commit -am "chore(release): 1.3.0"
git diff v1.3.0-rc.N --stat -- app alembic        # only app/__init__.py and the what's-new list
git tag -a v1.3.0 -m "Klopot 1.3.0"
git push && git push origin v1.3.0                  # CI publishes :v1.3.0 and :latest
gh release create v1.3.0 --latest --title "Klopot 1.3.0" --notes-file <changelog section>
scripts/deploy.sh 1.3.0
```

Then klopot.dev: version, badge, and anything announced as "next release".
