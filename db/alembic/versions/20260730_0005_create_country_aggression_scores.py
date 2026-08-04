"""create country_aggression_scores table for bilateral aggression component

Revision ID: 20260730_0005
Revises: 20260728_0004
Create Date: 2026-07-30 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_0005"
down_revision: Union[str, None] = "20260728_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "country_aggression_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("country_a", sa.String(length=3), nullable=False),
        sa.Column("country_b", sa.String(length=3), nullable=False),
        sa.Column("aggression_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("data_source", sa.Text(), nullable=False),
        sa.Column("baseline_source", sa.Text(), nullable=True),
        sa.Column("baseline_data_year", sa.Integer(), nullable=True),
        sa.Column("last_event_date", sa.Date(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("country_a", "country_b", name="uq_country_aggression_scores_pair"),
    )
    op.create_index("ix_country_aggression_scores_country_a", "country_aggression_scores", ["country_a"])
    op.create_index("ix_country_aggression_scores_country_b", "country_aggression_scores", ["country_b"])
    op.create_index("ix_country_aggression_scores_pair", "country_aggression_scores", ["country_a", "country_b"])


def downgrade() -> None:
    op.drop_index("ix_country_aggression_scores_pair", table_name="country_aggression_scores")
    op.drop_index("ix_country_aggression_scores_country_b", table_name="country_aggression_scores")
    op.drop_index("ix_country_aggression_scores_country_a", table_name="country_aggression_scores")
    op.drop_table("country_aggression_scores")
