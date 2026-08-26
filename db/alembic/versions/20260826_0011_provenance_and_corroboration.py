"""Phase 6 Data Layer: Provenance model, commodity market observations, and source validation constraints.

Revision ID: 20260826_0011
Revises: 20260826_0010
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260826_0011"
down_revision: Union[str, None] = "20260826_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_table_names(conn) -> set[str]:
    inspector = sa.inspect(conn)
    return set(inspector.get_table_names())


def _get_existing_column_names(conn, table_name: str) -> set[str]:
    inspector = sa.inspect(conn)
    try:
        columns = inspector.get_columns(table_name)
        return {c["name"] for c in columns}
    except Exception:
        return set()


def _get_existing_check_constraints(conn, table_name: str) -> set[str]:
    inspector = sa.inspect(conn)
    try:
        checks = inspector.get_check_constraints(table_name)
        return {c["name"] for c in checks if c.get("name")}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_table_names(conn)

    # 1. source_provenance table
    if "source_provenance" not in tables:
        op.create_table(
            "source_provenance",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("source_name", sa.String(length=64), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.Column("source_record_id", sa.String(length=128), nullable=True),
            sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("evidence_role", sa.String(length=64), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("raw_payload", JSONB, nullable=True),
            sa.Column("entity_type", sa.String(length=64), nullable=True),
            sa.Column("entity_id", sa.String(length=64), nullable=True),
            sa.UniqueConstraint("source_name", "source_record_id", "entity_type", name="uq_source_provenance_record_entity"),
        )
        op.create_index("ix_source_provenance_source_name", "source_provenance", ["source_name"])
        op.create_index("ix_source_provenance_entity", "source_provenance", ["entity_type", "entity_id"])
        op.create_index("ix_source_provenance_retrieved", "source_provenance", ["retrieved_at"])

    # 2. commodity_market_observations table
    if "commodity_market_observations" not in tables:
        op.create_table(
            "commodity_market_observations",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("source_name", sa.String(length=64), nullable=False),
            sa.Column("series_id", sa.String(length=128), nullable=False),
            sa.Column("commodity_code", sa.String(length=64), nullable=False),
            sa.Column("observation_date", sa.Date(), nullable=False),
            sa.Column("frequency", sa.String(length=32), nullable=False),
            sa.Column("value", sa.Numeric(14, 4), nullable=False),
            sa.Column("unit", sa.String(length=32), nullable=False),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.UniqueConstraint("source_name", "series_id", "observation_date", name="uq_commodity_obs_series_date"),
        )
        op.create_index("ix_commodity_obs_code_date", "commodity_market_observations", ["commodity_code", "observation_date"])
        op.create_index("ix_commodity_obs_source_date", "commodity_market_observations", ["source_name", "observation_date"])

    # 3. Add corroboration_status to commodity_news and government_actions
    cn_cols = _get_existing_column_names(conn, "commodity_news")
    if "corroboration_status" not in cn_cols:
        op.add_column("commodity_news", sa.Column("corroboration_status", sa.String(length=32), server_default="unavailable", nullable=False))
    cn_checks = _get_existing_check_constraints(conn, "commodity_news")
    if "ck_commodity_news_corroboration_status" not in cn_checks:
        op.create_check_constraint(
            "ck_commodity_news_corroboration_status",
            "commodity_news",
            "corroboration_status IN ('corroborated', 'neutral', 'inconsistent', 'unavailable')",
        )

    ga_cols = _get_existing_column_names(conn, "government_actions")
    if "corroboration_status" not in ga_cols:
        op.add_column("government_actions", sa.Column("corroboration_status", sa.String(length=32), server_default="unavailable", nullable=False))
    ga_checks = _get_existing_check_constraints(conn, "government_actions")
    if "ck_government_actions_corroboration_status" not in ga_checks:
        op.create_check_constraint(
            "ck_government_actions_corroboration_status",
            "government_actions",
            "corroboration_status IN ('corroborated', 'neutral', 'inconsistent', 'unavailable')",
        )

    # 4. Update check constraints on validation_source across tables
    # Protests
    pr_checks = _get_existing_check_constraints(conn, "protests")
    if "ck_protests_validation_source" in pr_checks:
        op.drop_constraint("ck_protests_validation_source", "protests", type_="check")
    op.create_check_constraint(
        "ck_protests_validation_source",
        "protests",
        "validation_source IS NULL OR validation_source IN ('groq', 'gemini', 'rules', 'legacy_import', 'acled', 'portwatch')",
    )

    # Government Actions
    if "ck_government_actions_validation_source" in ga_checks:
        op.drop_constraint("ck_government_actions_validation_source", "government_actions", type_="check")
    op.create_check_constraint(
        "ck_government_actions_validation_source",
        "government_actions",
        "validation_source IS NULL OR validation_source IN ('groq', 'gemini', 'rules', 'legacy_import', 'acled', 'portwatch')",
    )

    # Commodity News
    if "ck_commodity_news_validation_source" in cn_checks:
        op.drop_constraint("ck_commodity_news_validation_source", "commodity_news", type_="check")
    op.create_check_constraint(
        "ck_commodity_news_validation_source",
        "commodity_news",
        "validation_source IS NULL OR validation_source IN ('groq', 'gemini', 'rules', 'legacy_import', 'acled', 'portwatch')",
    )

    # Chokepoints (ensure validation_source column exists and has proper check constraint)
    chk_cols = _get_existing_column_names(conn, "chokepoints")
    if "validation_source" not in chk_cols:
        op.add_column("chokepoints", sa.Column("validation_source", sa.String(length=32), server_default="portwatch", nullable=True))
    chk_checks = _get_existing_check_constraints(conn, "chokepoints")
    if "ck_chokepoints_validation_source" not in chk_checks:
        op.create_check_constraint(
            "ck_chokepoints_validation_source",
            "chokepoints",
            "validation_source IS NULL OR validation_source IN ('portwatch', 'gdelt', 'rules', 'legacy_import')",
        )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_table_names(conn)

    if "commodity_market_observations" in tables:
        op.drop_table("commodity_market_observations")
    if "source_provenance" in tables:
        op.drop_table("source_provenance")

    cn_cols = _get_existing_column_names(conn, "commodity_news")
    if "corroboration_status" in cn_cols:
        op.drop_column("commodity_news", "corroboration_status")

    ga_cols = _get_existing_column_names(conn, "government_actions")
    if "corroboration_status" in ga_cols:
        op.drop_column("government_actions", "corroboration_status")
