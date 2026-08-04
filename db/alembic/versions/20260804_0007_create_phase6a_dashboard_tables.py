"""create phase 6a dashboard data layer tables

Revision ID: 20260804_0007
Revises: 20260731_0006
Create Date: 2026-08-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260804_0007"
down_revision: Union[str, None] = "20260731_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. tracked_commodities
    op.create_table(
        "tracked_commodities",
        sa.Column("commodity_code", sa.String(length=50), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("trade_type", sa.String(length=16), nullable=False),
        sa.Column("annual_value_usd", sa.Numeric(15, 2), nullable=False),
        sa.Column("source_citation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. chokepoints
    op.create_table(
        "chokepoints",
        sa.Column("code", sa.String(length=50), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("long", sa.Numeric(9, 6), nullable=False),
        sa.Column("baseline_mbd", sa.Numeric(8, 2), nullable=False),
        sa.Column("source_year", sa.Integer(), nullable=False),
        sa.Column("disruption_score", sa.Numeric(5, 2), server_default="0.0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="green", nullable=False),
        sa.Column("related_event_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=True),
        sa.Column("last_disruption_reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. world_boundaries
    op.create_table(
        "world_boundaries",
        sa.Column("iso_a3", sa.String(length=3), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("geojson", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4. regional_headlines
    op.create_table(
        "regional_headlines",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("gdelt_event_id", sa.BigInteger(), sa.ForeignKey("gdelt_events.global_event_id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("region", "rank", name="uq_regional_headlines_region_rank"),
    )
    op.create_index("ix_regional_headlines_region", "regional_headlines", ["region"])

    # 5. government_actions (India Government Policy Actions)
    op.create_table(
        "government_actions",
        sa.Column("rank", sa.SmallInteger(), primary_key=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("action_type", sa.String(length=64), server_default="diplomatic_policy", nullable=False),
        sa.Column("gdelt_event_id", sa.BigInteger(), sa.ForeignKey("gdelt_events.global_event_id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rank BETWEEN 1 AND 10", name="ck_government_actions_rank"),
    )

    # 6. protests
    op.create_table(
        "protests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("action_geo_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("action_geo_long", sa.Numeric(9, 6), nullable=True),
        sa.Column("gdelt_event_id", sa.BigInteger(), sa.ForeignKey("gdelt_events.global_event_id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("event_severity", sa.Numeric(5, 2), server_default="0.0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("city", "event_date", "headline", name="uq_protests_city_date_headline"),
    )
    op.create_index("ix_protests_date", "protests", ["event_date"])

    # 7. commodity_news
    op.create_table(
        "commodity_news",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("commodity_code", sa.String(length=50), sa.ForeignKey("tracked_commodities.commodity_code", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("gdelt_event_id", sa.BigInteger(), sa.ForeignKey("gdelt_events.global_event_id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("commodity_code", "rank", name="uq_commodity_news_commodity_rank"),
    )

    # 8. india_trade_routes
    op.create_table(
        "india_trade_routes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("commodity_code", sa.String(length=50), sa.ForeignKey("tracked_commodities.commodity_code", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_country", sa.String(length=3), nullable=False),
        sa.Column("primary_chokepoint", sa.String(length=50), sa.ForeignKey("chokepoints.code", ondelete="SET NULL"), nullable=True),
        sa.Column("origin_lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("origin_long", sa.Numeric(9, 6), nullable=False),
        sa.Column("dest_lat", sa.Numeric(9, 6), server_default="18.950000", nullable=False),
        sa.Column("dest_long", sa.Numeric(9, 6), server_default="72.950000", nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), server_default="0.0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("commodity_code", "partner_country", name="uq_india_trade_routes_commodity_partner"),
    )

    # 9. shipping_rates
    op.create_table(
        "shipping_rates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("route_id", sa.BigInteger(), sa.ForeignKey("india_trade_routes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("rate_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column("rate_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shipping_rates")
    op.drop_table("india_trade_routes")
    op.drop_table("commodity_news")
    op.drop_table("protests")
    op.drop_table("government_actions")
    op.drop_table("regional_headlines")
    op.drop_table("world_boundaries")
    op.drop_table("chokepoints")
    op.drop_table("tracked_commodities")
