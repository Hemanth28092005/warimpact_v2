"""create phase 2 tables for article cache and daily country signals

Revision ID: 20260727_0003
Revises: 20260727_0002
Create Date: 2026-07-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260727_0003"
down_revision: Union[str, None] = "20260727_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_text_cache",
        sa.Column("source_url", sa.Text(), primary_key=True),
        sa.Column("fetch_status", sa.String(length=32), nullable=False),
        sa.Column("article_text", sa.Text(), nullable=True),
        sa.Column("text_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_article_text_cache_status", "article_text_cache", ["fetch_status"])

    op.create_table(
        "country_daily_signals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("conflict_event_count", sa.Integer(), nullable=False),
        sa.Column("material_conflict_count", sa.Integer(), nullable=False),
        sa.Column("avg_goldstein", sa.Numeric(6, 3), nullable=True),
        sa.Column("weighted_conflict_intensity", sa.Numeric(12, 4), nullable=False),
        sa.Column("normalized_conflict_intensity", sa.Numeric(6, 4), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(6, 4), nullable=False),
        sa.Column("sentiment_sample_size", sa.Integer(), nullable=False),
        sa.Column("sentiment_confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("country_code", "signal_date", name="uq_country_daily_signals_country_date"),
    )
    op.create_index("ix_country_daily_signals_date", "country_daily_signals", ["signal_date"])
    op.create_index("ix_country_daily_signals_country", "country_daily_signals", ["country_code"])


def downgrade() -> None:
    op.drop_index("ix_country_daily_signals_country", table_name="country_daily_signals")
    op.drop_index("ix_country_daily_signals_date", table_name="country_daily_signals")
    op.drop_table("country_daily_signals")
    op.drop_index("ix_article_text_cache_status", table_name="article_text_cache")
    op.drop_table("article_text_cache")
