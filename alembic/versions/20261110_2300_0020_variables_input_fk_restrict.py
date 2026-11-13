"""variables.input_id FK: SET NULL -> RESTRICT

Audit B-01: deleting an input that a variable still references used to cascade
the child's input_id to NULL. A null binding means "accept any source", so the
delete silently widened a bound variable's trust. The delete handler already
refuses with a 409, but its app-level pre-check races a concurrent variable
insert: the insert commits, the delete commits, and SET NULL nulls the fresh
binding. Enforcing RESTRICT at the DB boundary refuses the delete regardless of
timing; the handler surfaces the refusal as the same 409. Explicit unbinding
stays an intentional UPDATE of input_id and is unaffected (RESTRICT only guards
the parent DELETE).

Forward-only: existing rows are untouched; only the constraint action changes.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-10 23:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK = "fk_variables_input_id_inputs"


def upgrade() -> None:
    with op.batch_alter_table("variables") as batch_op:
        batch_op.drop_constraint(_FK, type_="foreignkey")
        batch_op.create_foreign_key(
            _FK, "inputs", ["input_id"], ["id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    with op.batch_alter_table("variables") as batch_op:
        batch_op.drop_constraint(_FK, type_="foreignkey")
        batch_op.create_foreign_key(
            _FK, "inputs", ["input_id"], ["id"], ondelete="SET NULL"
        )
