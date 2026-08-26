"""World-monitor feature expansion: commodity prices, freight indices, seismic events, prediction markets.

Revision ID: 20260826_0009
Revises: 20260822_0008
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260826_0009"
down_revision: Union[str, None] = "20260822_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commodity_prices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("commodity_code", sa.String(length=50), sa.ForeignKey("tracked_commodities.commodity_code", ondelete="CASCADE"), nullable=False),
        sa.Column("price_usd", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_close_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("change_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("unit_label", sa.String(length=32), nullable=False, server_default="contract"),
        sa.Column("data_source", sa.String(length=50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("commodity_code", "observed_at", "data_source", name="uq_commodity_prices_code_observed_source"),
        sa.CheckConstraint("price_usd >= 0", name="ck_commodity_prices_nonnegative"),
    )
    op.create_index("ix_commodity_prices_code_observed", "commodity_prices", ["commodity_code", "observed_at"])

    op.create_table(
        "freight_indices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("index_code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("rate_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("previous_rate_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("change_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("unit_label", sa.String(length=64), nullable=False, server_default="per FEU"),
        sa.Column("route_label", sa.String(length=128), nullable=True),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("data_source", sa.String(length=50), nullable=False),
        sa.Column("is_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_citation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("index_code", "rate_date", "data_source", name="uq_freight_indices_code_date_source"),
        sa.CheckConstraint("rate_usd >= 0", name="ck_freight_indices_nonnegative"),
    )
    op.create_index("ix_freight_indices_code_date", "freight_indices", ["index_code", "rate_date"])

    op.create_table(
        "seismic_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("magnitude", sa.Numeric(4, 2), nullable=False),
        sa.Column("place", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("depth_km", sa.Numeric(8, 2), nullable=True),
        sa.Column("tsunami_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("near_chokepoint_code", sa.String(length=50), sa.ForeignKey("chokepoints.code", ondelete="SET NULL"), nullable=True),
        sa.Column("distance_to_chokepoint_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", sa.String(length=50), nullable=False, server_default="USGS"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("magnitude >= 0 AND magnitude <= 12", name="ck_seismic_events_magnitude_range"),
    )
    op.create_index("ix_seismic_events_occurred", "seismic_events", ["occurred_at"])
    op.create_index("ix_seismic_events_chokepoint", "seismic_events", ["near_chokepoint_code"])

    op.create_table(
        "prediction_markets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("market_slug", sa.String(length=191), nullable=False, unique=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False, server_default="polymarket"),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("yes_price", sa.Numeric(6, 4), nullable=True),
        sa.Column("volume_24h_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("yes_price IS NULL OR (yes_price >= 0 AND yes_price <= 1)", name="ck_prediction_markets_yes_price_range"),
    )
    op.create_index("ix_prediction_markets_fetched", "prediction_markets", ["fetched_at"])


def downgrade() -> None:
    op.drop_table("prediction_markets")
    op.drop_table("seismic_events")
    op.drop_table("freight_indices")
    op.drop_table("commodity_prices")
