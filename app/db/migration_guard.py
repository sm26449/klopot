"""Forward-only migration guard (audit V20).

alertd's migrations are forward-only. A per-migration ``downgrade()`` guard (e.g.
0008) can only protect its OWN DDL — by the time it raises, earlier steps of the
same ``alembic downgrade`` command have already run, and because MySQL DDL is not
transactional those drops are already committed. So a lossy downgrade could leave
the database half-torn-down even though one later step "refused".

This guard runs as a GLOBAL preflight: the migration steps are computed first, and
if any is a downgrade the whole command is refused BEFORE a single step executes —
unless the operator explicitly opts in with ``ALERTD_ALLOW_DOWNGRADE``. It does not
make a downgrade safe; the documented rollback path is restoring the pre-deploy
database backup (see docs/DEPLOY.md).
"""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}

REFUSAL_MESSAGE = (
    "Refusing a downgrade: alertd migrations are forward-only. A downgrade is NOT "
    "guaranteed non-destructive — MySQL DDL is not transactional, so a step that "
    "fails (or a later guard that raises) can leave tables already dropped. To roll "
    "back, restore the pre-deploy database backup (docs/DEPLOY.md § Rollback). To "
    "force the downgrade anyway, accepting possible data loss, set "
    "ALERTD_ALLOW_DOWNGRADE=1."
)


def downgrade_allowed() -> bool:
    """True only when the operator has explicitly opted in to downgrades."""
    return os.environ.get("ALERTD_ALLOW_DOWNGRADE", "").strip().lower() in _TRUTHY


def assert_no_unapproved_downgrade(steps) -> None:
    """Raise if any computed migration step is a downgrade and the override is
    not set. ``steps`` is the list alembic computed for this command, inspected
    before any of them executes."""
    if any(getattr(s, "is_downgrade", False) for s in steps) and not downgrade_allowed():
        raise RuntimeError(REFUSAL_MESSAGE)
