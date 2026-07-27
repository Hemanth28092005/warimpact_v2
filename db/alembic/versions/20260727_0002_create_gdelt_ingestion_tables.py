"""create gdelt ingestion tables

Revision ID: 20260727_0002
Revises: 20260723_0001
Create Date: 2026-07-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260727_0002"
down_revision: Union[str, None] = "20260723_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gdelt_events",
        sa.Column("global_event_id", sa.BigInteger(), primary_key=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_code", sa.String(length=16), nullable=True),
        sa.Column("event_base_code", sa.String(length=16), nullable=True),
        sa.Column("event_root_code", sa.String(length=16), nullable=True),
        sa.Column("quad_class", sa.SmallInteger(), nullable=True),
        sa.Column("goldstein_scale", sa.Numeric(6, 3), nullable=True),
        sa.Column("num_mentions", sa.Integer(), nullable=True),
        sa.Column("num_sources", sa.Integer(), nullable=True),
        sa.Column("num_articles", sa.Integer(), nullable=True),
        sa.Column("avg_tone", sa.Numeric(8, 4), nullable=True),
        sa.Column("actor1_country_code", sa.String(length=3), nullable=True),
        sa.Column("actor2_country_code", sa.String(length=3), nullable=True),
        sa.Column("actor1_type", sa.String(length=32), nullable=True),
        sa.Column("actor2_type", sa.String(length=32), nullable=True),
        sa.Column("action_geo_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("action_geo_long", sa.Numeric(9, 6), nullable=True),
        sa.Column("action_geo_country_code", sa.String(length=3), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("has_missing_actors", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gdelt_events_event_date", "gdelt_events", ["event_date"])
    op.create_index("ix_gdelt_events_action_geo_country_code", "gdelt_events", ["action_geo_country_code"])

    op.create_table(
        "source_health",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("feed_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("fetch_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetch_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_source_health_run_id", "source_health", ["run_id"])
    op.create_index("ix_source_health_source_feed", "source_health", ["source_name", "feed_name"])


def downgrade() -> None:
    op.drop_index("ix_source_health_source_feed", table_name="source_health")
    op.drop_index("ix_source_health_run_id", table_name="source_health")
    op.drop_table("source_health")
    op.drop_index("ix_gdelt_events_action_geo_country_code", table_name="gdelt_events")
    op.drop_index("ix_gdelt_events_event_date", table_name="gdelt_events")
    op.drop_table("gdelt_events")
