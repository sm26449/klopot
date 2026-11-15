"""Generic provider lifecycle: durable commands + inbound event inbox;
gotify and pushover channel kinds.

- ``lifecycle_commands``: an action owed to a provider about one delivery
  (e.g. cancel a Pushover emergency receipt after an acknowledgement),
  retried by the provider-lifecycle service, at most one per
  (delivery, action).
- ``inbound_events``: events received from providers (e.g. "receipt X was
  acknowledged in the Pushover app"), deduplicated by (provider, event_key)
  so each is applied exactly once.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_CHANNELS = ("ui", "banner", "telegram", "sms", "email", "push", "webhook", "mqtt", "ntfy")


def upgrade() -> None:
    op.create_table(
        "lifecycle_commands",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("delivery_id", sa.BigInteger(), sa.ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("ref", sa.String(255), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("delivery_id", "action", name="uq_lifecycle_command"),
    )
    op.create_index("ix_lifecycle_command_due", "lifecycle_commands", ["state", "next_attempt_at"])
    op.create_table(
        "inbound_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_key", sa.String(191), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("result", sa.String(64), nullable=True),
        sa.UniqueConstraint("provider", "event_key", name="uq_inbound_event"),
    )
    op.alter_column("channels", "kind",
        existing_type=sa.Enum(*_CHANNELS), type_=sa.Enum(*_CHANNELS, "gotify", "pushover"), existing_nullable=False)


def downgrade() -> None:
    raise RuntimeError("Migration 0029 is forward-only; restore the pre-deploy backup.")
