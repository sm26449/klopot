<!-- Thanks for contributing! Keep PRs focused — one feature or fix each. -->

## What and why

Describe the change and the problem it solves. Link any issue
(`Closes #123`).

## How it was tested

- [ ] `.venv/bin/python -m pytest -q`
- [ ] `node --test tests/js/*.mjs`
- [ ] `.venv/bin/ruff check app scripts`
- [ ] New/changed behaviour has a test that fails before the change and
      passes after.

Describe any manual verification (migrations run, UI checked, etc.).

## Checklist

- [ ] Conventional Commit messages, scope in parentheses, **no trailers**
      of any kind (see `CONTRIBUTING.md`).
- [ ] No secrets, hostnames, phone numbers or private IPs added.
- [ ] Migrations are forward-only (new revision, never edit a published
      one).
- [ ] New UI colours go through an ADR token (ADR-0001), not a literal.
- [ ] Docs updated if behaviour or the API changed.
