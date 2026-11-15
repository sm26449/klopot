"""Throttle state per pool: real fires and test fires (public-exposure review).

``throttle_state`` held one row per template type, shared by real and test
fires, while the duplicate claims (``dedup_claims``) already kept the two
apart by ``is_test``. A test fire therefore had to skip the throttle and the
per-type cooldown altogether — or it would throttle the type's next real
alert. That skip made ``test: true`` on ``/v1/fire`` an unthrottled pager for
any ``fire`` key.

Now the key is ``(type, is_test)``: a test fire is throttled among test fires
and never delays a real alert. Existing rows are real-fire state
(``is_test = false``). Only an administrator's test still skips the gates
(``FireEnvelope.override_silencing``).

Revision ID: 0040
Revises: 0039
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("throttle_state") as batch:
        batch.add_column(sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()))
    if op.get_bind().dialect.name == "mysql":
        # One statement, so the table is never without a primary key.
        op.execute("ALTER TABLE throttle_state DROP PRIMARY KEY, ADD PRIMARY KEY (type, is_test)")
    else:
        with op.batch_alter_table("throttle_state", recreate="always") as batch:
            batch.create_primary_key("pk_throttle_state", ["type", "is_test"])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM throttle_state WHERE is_test = :t").bindparams(t=True))
    if op.get_bind().dialect.name == "mysql":
        op.execute("ALTER TABLE throttle_state DROP PRIMARY KEY, ADD PRIMARY KEY (type)")
    else:
        with op.batch_alter_table("throttle_state", recreate="always") as batch:
            batch.create_primary_key("pk_throttle_state", ["type"])
    with op.batch_alter_table("throttle_state") as batch:
        batch.drop_column("is_test")
