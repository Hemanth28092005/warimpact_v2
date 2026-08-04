"""create cii_model_registry table for tracking model versions, metrics, and active model promotion

Revision ID: 20260731_0006
Revises: 20260730_0005
Create Date: 2026-07-31 10:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260731_0006"
down_revision: Union[str, None] = "20260730_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cii_model_registry",
        sa.Column("model_version", sa.String(length=50), primary_key=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_date_start", sa.Date(), nullable=False),
        sa.Column("train_date_end", sa.Date(), nullable=False),
        sa.Column("val_date_start", sa.Date(), nullable=False),
        sa.Column("val_date_end", sa.Date(), nullable=False),
        sa.Column("in_scope_countries_count", sa.Integer(), nullable=False),
        sa.Column("train_samples_count", sa.Integer(), nullable=False),
        sa.Column("val_samples_count", sa.Integer(), nullable=False),
        sa.Column("regressor_type", sa.String(length=50), nullable=False),
        sa.Column("val_rmse", sa.Numeric(8, 4), nullable=False),
        sa.Column("val_mae", sa.Numeric(8, 4), nullable=False),
        sa.Column("val_r2", sa.Numeric(8, 4), nullable=False),
        sa.Column("baseline_rmse", sa.Numeric(8, 4), nullable=False),
        sa.Column("classifier_type", sa.String(length=50), nullable=False),
        sa.Column("val_roc_auc", sa.Numeric(8, 4), nullable=False),
        sa.Column("baseline_roc_auc", sa.Numeric(8, 4), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),  # 'promoted', 'held_back', 'initial'
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("promotion_notes", sa.Text(), nullable=True),
        sa.Column("metadata_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cii_model_registry_is_active", "cii_model_registry", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_cii_model_registry_is_active", table_name="cii_model_registry")
    op.drop_table("cii_model_registry")
