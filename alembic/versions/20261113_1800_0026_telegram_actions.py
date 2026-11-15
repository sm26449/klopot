"""Telegram provider receipts, callback capabilities, inbox and durable commands.

Revision ID: 0026
Revises: 0025
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deliveries", sa.Column("action_keyboard", sa.JSON(), nullable=True))
    op.create_table("telegram_bot_state",
        sa.Column("bot_key", sa.String(64), primary_key=True),
        sa.Column("next_offset", sa.BigInteger(), nullable=False),
        sa.Column("last_update_at", sa.DateTime()),
    )
    op.create_table("channel_action_tokens",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("delivery_id", sa.BigInteger(), sa.ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("bot_key", sa.String(64), nullable=False),
        sa.Column("chat_id", sa.String(64), nullable=False),
        sa.Column("allowed_user_ids", sa.JSON(), nullable=False),
        sa.Column("any_chat_member", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()),
    )
    op.create_index("ix_channel_action_tokens_delivery_id", "channel_action_tokens", ["delivery_id"])
    op.create_table("channel_provider_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("delivery_id", sa.BigInteger(), sa.ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("bot_key", sa.String(64), nullable=False),
        sa.Column("chat_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("view_url", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "bot_key", "chat_id", "message_id", name="uq_provider_message"),
    )
    op.create_index("ix_channel_provider_messages_delivery_id", "channel_provider_messages", ["delivery_id"])
    op.create_table("channel_action_commands",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("delivery_id", sa.BigInteger(), sa.ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_name", sa.String(64), nullable=False),
        sa.Column("snooze_until", sa.DateTime()),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime()),
        sa.Column("last_error", sa.String(500)),
        sa.Column("applied_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_action_command_due", "channel_action_commands", ["state", "next_attempt_at"])
    op.create_table("channel_events",
        sa.Column("bot_key", sa.String(64), primary_key=True),
        sa.Column("update_id", sa.BigInteger(), primary_key=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("command_id", sa.String(64), sa.ForeignKey("channel_action_commands.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_channel_events_created_at", "channel_events", ["created_at"])
    op.create_table("channel_provider_commands",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("reference_id", sa.BigInteger(), sa.ForeignKey("channel_provider_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime()),
        sa.Column("last_error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("reference_id", "operation", name="uq_provider_command"),
    )
    op.create_index("ix_provider_command_due", "channel_provider_commands", ["state", "next_attempt_at"])


def downgrade() -> None:
    raise RuntimeError("Telegram action migration is forward-only; restore the pre-deploy backup.")
