"""Activity log: delivery attempts, API requests, system events.

Three append-only tables, written off the hot path by app.core.activity and
swept by retention with ``log_retention_days`` (docs/ACTIVITY_LOG.md).

Revision ID: 0032
Revises: 0031
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_LONG_TEXT = sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


def upgrade() -> None:
    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("delivery_id", sa.BigInteger(), sa.ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=True),
        sa.Column("notification_id", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("retry_after_sec", sa.Integer(), nullable=True),
        sa.Column("provider_ref", sa.String(255), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("exchange", sa.JSON(), nullable=True),
    )
    op.create_index("ix_attempts_delivery", "delivery_attempts", ["delivery_id"])
    op.create_index("ix_attempts_notification", "delivery_attempts", ["notification_id"])
    op.create_index("ix_attempts_channel_ts", "delivery_attempts", ["channel", "started_at"])
    op.create_index("ix_attempts_ts", "delivery_attempts", ["started_at"])

    op.create_table(
        "api_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("route", sa.String(191), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actor_kind", sa.String(16), nullable=True),
        sa.Column("actor_name", sa.String(64), nullable=True),
        sa.Column("api_key_id", sa.BigInteger(), nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("trace_id", sa.String(40), nullable=True),
        sa.Column("request_body", _LONG_TEXT, nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_api_requests_expires", "api_requests", ["expires_at"])
    op.create_index("ix_api_requests_ts", "api_requests", ["ts"])
    op.create_index("ix_api_requests_route_ts", "api_requests", ["route", "ts"])
    op.create_index("ix_api_requests_status_ts", "api_requests", ["status", "ts"])
    op.create_index("ix_api_requests_trace", "api_requests", ["trace_id"])

    rules = op.create_table(
        "activity_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("match_method", sa.String(8), nullable=True),
        sa.Column("match_path", sa.String(191), nullable=False, server_default="*"),
        sa.Column("match_status", sa.String(8), nullable=True),
        sa.Column("match_actor", sa.String(64), nullable=True),
        sa.Column("match_ip", sa.String(64), nullable=True),
        sa.Column("action", sa.String(8), nullable=False, server_default="keep"),
        sa.Column("keep_days", sa.Integer(), nullable=True),
        sa.Column("request_body", sa.String(8), nullable=False, server_default="auto"),
        sa.Column("response_body", sa.String(8), nullable=False, server_default="auto"),
        sa.Column("hits", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(), nullable=True),
        sa.Column("last_ip", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_activity_rules_position", "activity_rules", ["position"])
    # Health / metrics probes stay visible (one day) instead of piling up for 90.
    op.bulk_insert(rules, [{"name": "Health & metrics probes", "enabled": True, "position": 10,
                            "match_method": "GET", "match_path": "/v1/health*", "action": "keep",
                            "keep_days": 1, "request_body": "never", "response_body": "never"},
                           {"name": "Prometheus scrape", "enabled": True, "position": 11,
                            "match_method": "GET", "match_path": "/v1/metrics*", "action": "keep",
                            "keep_days": 1, "request_body": "never", "response_body": "never"}])

    op.create_table(
        "system_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("detail", sa.String(500), nullable=True),
    )
    op.create_index("ix_system_events_ts", "system_events", ["ts"])
    op.create_index("ix_system_events_source", "system_events", ["source_kind", "source_id", "ts"])


def downgrade() -> None:
    op.drop_table("system_events")
    op.drop_table("activity_rules")
    op.drop_table("api_requests")
    op.drop_table("delivery_attempts")
