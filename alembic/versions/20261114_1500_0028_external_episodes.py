"""External episodes, provider references, Alertmanager input, ntfy channel.

- ``incidents`` gain a generic source: ``source_kind`` (rule / fire /
  alertmanager), ``source_key`` (the episode identity) and
  ``active_source_key`` — unique while the episode is open, cleared on
  resolution, like ``active_rule_id`` — plus ``source_started_at`` so a late
  resolution cannot close a newer episode.
- ``deliveries.provider_ref``: the provider's id for a sent message (e.g. the
  ntfy message id), when the channel reports one.
- ``inputs.kind`` += ``alertmanager``; ``channels.kind`` += ``ntfy``.

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_INPUTS = ("mqtt", "http_poll", "webhook", "schedule", "sms_inbox", "email_imap")
_CHANNELS = ("ui", "banner", "telegram", "sms", "email", "push", "webhook", "mqtt")


def upgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("source_kind", sa.String(32), nullable=False, server_default="rule"))
        batch.add_column(sa.Column("source_key", sa.String(191), nullable=True))
        batch.add_column(sa.Column("active_source_key", sa.String(191), nullable=True))
        batch.add_column(sa.Column("source_started_at", sa.DateTime(), nullable=True))
        batch.create_unique_constraint("uq_incident_active_source", ["active_source_key"])
        batch.create_index("ix_incident_source_key", ["source_key"])
    with op.batch_alter_table("deliveries") as batch:
        batch.add_column(sa.Column("provider_ref", sa.String(255), nullable=True))
    op.alter_column("inputs", "kind",
        existing_type=sa.Enum(*_INPUTS), type_=sa.Enum(*_INPUTS, "alertmanager"), existing_nullable=False)
    op.alter_column("channels", "kind",
        existing_type=sa.Enum(*_CHANNELS), type_=sa.Enum(*_CHANNELS, "ntfy"), existing_nullable=False)


def downgrade() -> None:
    raise RuntimeError("Migration 0028 is forward-only; restore the pre-deploy backup.")
