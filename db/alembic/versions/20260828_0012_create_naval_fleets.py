"""Create naval_fleets table for strategic naval fleet & strike group tracking.

Revision ID: 20260828_0012
Revises: 20260826_0011
Create Date: 2026-08-28 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260828_0012"
down_revision: Union[str, None] = "20260826_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "naval_fleets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=16), nullable=False),
        sa.Column("flag_country", sa.String(length=64), nullable=False),
        sa.Column("fleet_type", sa.String(length=32), nullable=False),
        sa.Column("flagship", sa.String(length=128), nullable=False),
        sa.Column("composition", sa.Text(), nullable=True),
        sa.Column("operational_area", sa.String(length=128), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="deployed"),
        sa.Column("threat_level", sa.String(length=16), nullable=False, server_default="routine"),
        sa.Column("mission_brief", sa.Text(), nullable=True),
        sa.Column("source_citation", sa.Text(), nullable=True),
        sa.Column("last_reported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_naval_fleets_country", "naval_fleets", ["country_code"])
    op.create_index("ix_naval_fleets_type", "naval_fleets", ["fleet_type"])
    op.create_index("ix_naval_fleets_status", "naval_fleets", ["status"])


def downgrade() -> None:
    op.drop_table("naval_fleets")
