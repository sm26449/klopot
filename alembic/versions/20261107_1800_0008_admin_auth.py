"""admin_auth

Human authentication for the standalone admin UI
(docs/ADMIN_UI_AUDIT_AND_PLAN.md, phase F1):

- ``admin_users`` — browser accounts (argon2id hashes); v1 seeds one.
- ``admin_sessions`` — opaque sessions (sha256 of the cookie token).
- ``login_attempts`` — lockout source, pruned by retention.
- ``audit_log.actor_kind`` gains the ``user`` value.

Additive only; the previous image ignores the new tables.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07 18:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_ACTOR_KIND = sa.Enum("api_key", "jwt", "system", name="actorkind")
_NEW_ACTOR_KIND = sa.Enum("api_key", "jwt", "system", "user", name="actorkind")


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_sessions_user_active", "admin_sessions", ["user_id", "revoked_at", "expires_at"]
    )

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attempts_user_ts", "login_attempts", ["username", "ts"])
    op.create_index("ix_attempts_ip_ts", "login_attempts", ["ip", "ts"])

    # MySQL ENUM: adding a value is an in-place ALTER (no row rewrite
    # because the existing values keep their ordinal positions).
    op.alter_column(
        "audit_log",
        "actor_kind",
        existing_type=_OLD_ACTOR_KIND,
        type_=_NEW_ACTOR_KIND,
        existing_nullable=False,
    )


def downgrade() -> None:
    # Rows with actor_kind='user' would be TRUNCATED by MySQL on the narrowing
    # ALTER (error 1265), and MySQL DDL is not transactional, so a downgrade
    # that failed mid-way would have already dropped the admin tables. Reject
    # the downgrade up front when such rows exist (audit F42) — this project
    # is forward-only; archive/remap user audit rows before downgrading.
    bind = op.get_bind()
    user_rows = bind.execute(
        sa.text("SELECT COUNT(*) FROM audit_log WHERE actor_kind = 'user'")
    ).scalar()
    if user_rows:
        raise RuntimeError(
            f"Refusing downgrade 0008→0007: {user_rows} audit_log row(s) have "
            "actor_kind='user', which this narrowing migration cannot preserve. "
            "Archive or remap those rows first (forward-only migration policy)."
        )
    op.alter_column(
        "audit_log",
        "actor_kind",
        existing_type=_NEW_ACTOR_KIND,
        type_=_OLD_ACTOR_KIND,
        existing_nullable=False,
    )
    # Dropping a table drops its indexes; an explicit drop_index on
    # ix_sessions_user_active fails on MySQL (1553) because InnoDB
    # reuses that composite index for the user_id foreign key.
    op.drop_table("login_attempts")
    op.drop_table("admin_sessions")
    op.drop_table("admin_users")
