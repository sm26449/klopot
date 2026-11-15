"""Add the MQTT output channel without changing existing channel rows.

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("channels", "kind",
        existing_type=sa.Enum("ui", "banner", "telegram", "sms", "email", "push", "webhook"),
        type_=sa.Enum("ui", "banner", "telegram", "sms", "email", "push", "webhook", "mqtt"),
        existing_nullable=False)


def downgrade() -> None:
    raise RuntimeError("MQTT output migration is forward-only; restore the pre-deploy backup.")
