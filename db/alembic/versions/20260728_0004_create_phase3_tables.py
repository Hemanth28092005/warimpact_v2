"""create phase 3 tables for cii training labels and country instability index

Revision ID: 20260728_0004
Revises: 20260727_0003
Create Date: 2026-07-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260728_0004"
down_revision: Union[str, None] = "20260727_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cii_training_labels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("label_date", sa.Date(), nullable=False),
        sa.Column("fsi_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("escalation_label", sa.Integer(), nullable=False),
        sa.Column("label_source", sa.Text(), nullable=False),
        sa.Column("label_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("country_code", "label_date", name="uq_cii_training_labels_country_date"),
    )
    op.create_index("ix_cii_training_labels_date", "cii_training_labels", ["label_date"])
    op.create_index("ix_cii_training_labels_country", "cii_training_labels", ["country_code"])

    op.create_table(
        "country_instability_index",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("cii_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("feature_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_interval_low", sa.Numeric(5, 2), nullable=False),
        sa.Column("confidence_interval_high", sa.Numeric(5, 2), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("country_code", "score_date", "model_version", name="uq_country_instability_index_country_date_model"),
    )
    op.create_index("ix_country_instability_index_date", "country_instability_index", ["score_date"])
    op.create_index("ix_country_instability_index_country", "country_instability_index", ["country_code"])


def downgrade() -> None:
    op.drop_index("ix_country_instability_index_country", table_name="country_instability_index")
    op.drop_index("ix_country_instability_index_date", table_name="country_instability_index")
    op.drop_table("country_instability_index")
    op.drop_index("ix_cii_training_labels_country", table_name="cii_training_labels")
    op.drop_index("ix_cii_training_labels_date", table_name="cii_training_labels")
    op.drop_table("cii_training_labels")
