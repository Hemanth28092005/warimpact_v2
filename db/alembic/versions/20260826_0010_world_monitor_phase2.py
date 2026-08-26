"""World monitor phase 2: military flights, static intel sites and cable routes.

Revision ID: 20260826_0010
Revises: 20260826_0009
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260826_0010"
down_revision: Union[str, None] = "20260826_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "military_flights",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hex_code", sa.String(length=16), nullable=False, unique=True),
        sa.Column("registration", sa.String(length=32), nullable=True),
        sa.Column("aircraft_type", sa.String(length=16), nullable=True),
        sa.Column("callsign", sa.String(length=16), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("altitude_ft", sa.Integer(), nullable=True),
        sa.Column("ground_speed_kt", sa.Numeric(8, 2), nullable=True),
        sa.Column("squawk", sa.String(length=8), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", sa.String(length=50), nullable=False, server_default="ADSB_LOL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_military_flights_observed", "military_flights", ["observed_at"])

    op.create_table(
        "intel_sites",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("source_citation", sa.Text(), nullable=True),
        sa.Column("is_estimated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("category", "name", name="uq_intel_sites_category_name"),
        sa.CheckConstraint(
            "category IN ('military_base', 'nuclear_site', 'spaceport', 'chokepoint_node')",
            name="ck_intel_sites_category",
        ),
    )
    op.create_index("ix_intel_sites_category", "intel_sites", ["category"])

    op.create_table(
        "intel_routes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("from_name", sa.String(length=64), nullable=False),
        sa.Column("from_lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("from_long", sa.Numeric(9, 6), nullable=False),
        sa.Column("to_name", sa.String(length=64), nullable=False),
        sa.Column("to_lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("to_long", sa.Numeric(9, 6), nullable=False),
        sa.Column("source_citation", sa.Text(), nullable=True),
        sa.Column("is_estimated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("category", "name", name="uq_intel_routes_category_name"),
        sa.CheckConstraint("category IN ('undersea_cable', 'pipeline')", name="ck_intel_routes_category"),
    )


def downgrade() -> None:
    op.drop_table("intel_routes")
    op.drop_table("intel_sites")
    op.drop_table("military_flights")
