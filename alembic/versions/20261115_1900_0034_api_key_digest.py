"""API keys: an indexed digest, so a key is found without bcrypt (audit P07).

``key_digest`` is the SHA-256 of a generated key. Authentication looks a key
up by it first; bcrypt runs only for rows without one — keys issued before
this revision, whose digest is written on their first successful use (the
plaintext is not stored, so it cannot be backfilled here), and keys chosen by
the operator, which never get one.

Revision ID: 0034
Revises: 0033
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("key_digest", sa.String(64), nullable=True))
    op.create_index("uq_api_keys_key_digest", "api_keys", ["key_digest"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_api_keys_key_digest", table_name="api_keys")
    op.drop_column("api_keys", "key_digest")
