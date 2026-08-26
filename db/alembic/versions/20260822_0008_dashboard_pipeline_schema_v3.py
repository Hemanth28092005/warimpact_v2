"""Dashboard data pipeline and schema fix v3 migration.

Revision ID: 20260822_0008
Revises: 20260804_0007
Create Date: 2026-08-22 00:00:00.000000

Features:
- Schema introspection and provenance tracking (_migration_0008_provenance) for safe upgrade/downgrade reconciliation.
- Comprehensive CHECK constraints on all dashboard and model tables.
- Provenance-aware downgrade preserving pre-existing drifted columns.
- Deterministic ctid-based article_text_cache deduplication prioritizing successful text.
- Persistent story deduplication table (news_stories).
- Chokepoint child evidence table (chokepoint_events) with uniqueness and indexing.
- Dedicated cascade run state model table (cascade_runs) and cascade_scores schema.
- Canonical controlled vocabularies (chokepoints green/yellow/red, government actions canonical action_types).
- Protest geography schema overhaul (location_name, location_level, nullable city, state, country_code).
- Article cache canonical URL migration and retry/freshness metadata.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260822_0008"
down_revision: Union[str, None] = "20260804_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_column_names(conn, table_name: str) -> set[str]:
    """Inspect existing columns on a table safely."""
    inspector = sa.inspect(conn)
    try:
        columns = inspector.get_columns(table_name)
        return {c["name"] for c in columns}
    except Exception:
        return set()


def _get_existing_table_names(conn) -> set[str]:
    """Inspect existing tables in public schema."""
    inspector = sa.inspect(conn)
    return set(inspector.get_table_names())


def _get_existing_check_constraints(conn, table_name: str) -> set[str]:
    """Inspect existing check constraints on a table."""
    inspector = sa.inspect(conn)
    try:
        checks = inspector.get_check_constraints(table_name)
        return {c["name"] for c in checks if c.get("name")}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_table_names(conn)

    # 0. Create provenance table to track exactly what migration 0008 adds
    if "_migration_0008_provenance" not in tables:
        op.create_table(
            "_migration_0008_provenance",
            sa.Column("object_type", sa.String(length=32), nullable=False),  # 'table', 'column', 'constraint', 'index'
            sa.Column("table_name", sa.String(length=64), nullable=False),
            sa.Column("object_name", sa.String(length=64), nullable=False),
            sa.PrimaryKeyConstraint("object_type", "table_name", "object_name"),
        )

    def record_provenance(obj_type: str, tbl_name: str, obj_name: str) -> None:
        op.execute(
            sa.text(
                "INSERT INTO _migration_0008_provenance (object_type, table_name, object_name) "
                "VALUES (:obj_type, :tbl_name, :obj_name) ON CONFLICT DO NOTHING"
            ).bindparams(obj_type=obj_type, tbl_name=tbl_name, obj_name=obj_name)
        )

    # 1. Persistent story deduplication table (news_stories)
    if "news_stories" not in tables:
        op.create_table(
            "news_stories",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("canonical_url", sa.Text(), nullable=False, unique=True),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("normalized_title", sa.Text(), nullable=False),
            sa.Column("source_domain", sa.String(length=128), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_news_stories_canonical_url", "news_stories", ["canonical_url"])
        op.create_index("ix_news_stories_content_hash", "news_stories", ["content_hash"])
        op.create_index("ix_news_stories_source_domain", "news_stories", ["source_domain"])
        record_provenance("table", "news_stories", "news_stories")

    # 2. Chokepoint child evidence table (chokepoint_events)
    if "chokepoint_events" not in tables:
        op.create_table(
            "chokepoint_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("chokepoint_code", sa.String(length=50), sa.ForeignKey("chokepoints.code", ondelete="CASCADE"), nullable=False),
            sa.Column("gdelt_event_id", sa.BigInteger(), sa.ForeignKey("gdelt_events.global_event_id", ondelete="SET NULL"), nullable=True),
            sa.Column("distance_km", sa.Numeric(8, 2), nullable=False),
            sa.Column("contribution_score", sa.Numeric(5, 2), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("chokepoint_code", "gdelt_event_id", "observed_at", name="uq_chokepoint_events_code_event_date"),
        )
        op.create_index("ix_chokepoint_events_code_observed", "chokepoint_events", ["chokepoint_code", "observed_at"])
        record_provenance("table", "chokepoint_events", "chokepoint_events")

    # 3. Cascade Run State Tracking table (cascade_runs)
    if "cascade_runs" not in tables:
        op.create_table(
            "cascade_runs",
            sa.Column("run_id", sa.Uuid(), primary_key=True),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("calculation_status", sa.String(length=32), nullable=False),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("cii_max_score_date", sa.Date(), nullable=True),
            sa.Column("source_data_freshness_hours", sa.Numeric(6, 2), nullable=True),
            sa.Column("model_version", sa.String(length=64), nullable=True),
            sa.Column("window_days", sa.Integer(), server_default="7", nullable=False),
            sa.Column("pairs_calculated", sa.Integer(), server_default="0", nullable=False),
            sa.Column("pairs_published", sa.Integer(), server_default="0", nullable=False),
            sa.CheckConstraint(
                "calculation_status IN ('computed', 'no_spikes', 'insufficient_data', 'stale_input', 'failed')",
                name="ck_cascade_runs_status",
            ),
        )
        op.create_index("ix_cascade_runs_started_at", "cascade_runs", ["started_at"])
        record_provenance("table", "cascade_runs", "cascade_runs")

    # 4. cascade_scores table definition
    if "cascade_scores" not in tables:
        op.create_table(
            "cascade_scores",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("source_country", sa.String(length=3), nullable=False),
            sa.Column("target_country", sa.String(length=3), nullable=False),
            sa.Column("contagion_score", sa.Float(), nullable=False),
            sa.Column("co_spike_count", sa.Integer(), nullable=False),
            sa.Column("source_spike_count", sa.Integer(), nullable=False),
            sa.Column("window_days", sa.Integer(), nullable=False),
            sa.Column("analysis_start_date", sa.Date(), nullable=False),
            sa.Column("analysis_end_date", sa.Date(), nullable=False),
            sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("run_id", sa.Uuid(), sa.ForeignKey("cascade_runs.run_id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("source_country", "target_country", "window_days", name="uq_cascade_scores_pair_window"),
        )
        op.create_index("ix_cascade_scores_source", "cascade_scores", ["source_country"])
        record_provenance("table", "cascade_scores", "cascade_scores")
    else:
        cascade_cols = _get_existing_column_names(conn, "cascade_scores")
        if "run_id" not in cascade_cols:
            op.add_column("cascade_scores", sa.Column("run_id", sa.Uuid(), sa.ForeignKey("cascade_runs.run_id", ondelete="SET NULL"), nullable=True))
            record_provenance("column", "cascade_scores", "run_id")

    cs_checks = _get_existing_check_constraints(conn, "cascade_scores")
    if "ck_cascade_scores_contagion" not in cs_checks:
        op.create_check_constraint("ck_cascade_scores_contagion", "cascade_scores", "contagion_score >= 0.0 AND contagion_score <= 1.0")
        record_provenance("constraint", "cascade_scores", "ck_cascade_scores_contagion")

    # 5. regional_headlines drift reconciliation & check constraints
    rh_cols = _get_existing_column_names(conn, "regional_headlines")
    for col_name, col_type, nullable, default in [
        ("story_id", sa.BigInteger(), True, None),
        ("llm_brief", sa.Text(), True, None),
        ("validation_source", sa.String(length=32), True, None),
        ("brief_source", sa.String(length=32), True, "none"),
        ("confidence", sa.Numeric(4, 3), True, None),
        ("relevance_reason", sa.Text(), True, None),
    ]:
        if col_name not in rh_cols:
            op.add_column("regional_headlines", sa.Column(col_name, col_type, server_default=default, nullable=nullable))
            record_provenance("column", "regional_headlines", col_name)
        elif col_name == "validation_source":
            op.alter_column("regional_headlines", "validation_source", existing_type=sa.String(10), type_=sa.String(32))

    # Normalize existing legacy values
    op.execute("UPDATE regional_headlines SET validation_source = 'legacy_import' WHERE validation_source IS NOT NULL AND validation_source NOT IN ('groq', 'gemini', 'rules', 'legacy_import');")
    op.execute("UPDATE regional_headlines SET brief_source = 'legacy_unverified' WHERE brief_source IS NOT NULL AND brief_source NOT IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none');")

    rh_checks = _get_existing_check_constraints(conn, "regional_headlines")
    if "ck_regional_headlines_rank" not in rh_checks:
        op.create_check_constraint("ck_regional_headlines_rank", "regional_headlines", "rank BETWEEN 1 AND 10")
        record_provenance("constraint", "regional_headlines", "ck_regional_headlines_rank")
    if "ck_regional_headlines_confidence" not in rh_checks:
        op.create_check_constraint("ck_regional_headlines_confidence", "regional_headlines", "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)")
        record_provenance("constraint", "regional_headlines", "ck_regional_headlines_confidence")
    if "ck_regional_headlines_validation_source" not in rh_checks:
        op.create_check_constraint("ck_regional_headlines_validation_source", "regional_headlines", "validation_source IS NULL OR validation_source IN ('groq', 'gemini', 'rules', 'legacy_import')")
        record_provenance("constraint", "regional_headlines", "ck_regional_headlines_validation_source")
    if "ck_regional_headlines_brief_source" not in rh_checks:
        op.create_check_constraint("ck_regional_headlines_brief_source", "regional_headlines", "brief_source IS NULL OR brief_source IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none')")
        record_provenance("constraint", "regional_headlines", "ck_regional_headlines_brief_source")

    # 6. government_actions drift reconciliation & check constraints
    ga_cols = _get_existing_column_names(conn, "government_actions")
    for col_name, col_type, nullable, default in [
        ("story_id", sa.BigInteger(), True, None),
        ("llm_brief", sa.Text(), True, None),
        ("validation_source", sa.String(length=32), True, None),
        ("brief_source", sa.String(length=32), True, "none"),
        ("confidence", sa.Numeric(4, 3), True, None),
        ("relevance_reason", sa.Text(), True, None),
        ("actor_entity", sa.String(length=128), True, None),
    ]:
        if col_name not in ga_cols:
            op.add_column("government_actions", sa.Column(col_name, col_type, server_default=default, nullable=nullable))
            record_provenance("column", "government_actions", col_name)
        elif col_name == "validation_source":
            op.alter_column("government_actions", "validation_source", existing_type=sa.String(10), type_=sa.String(32))

    # Migrate legacy action_type values & validation sources
    op.execute("UPDATE government_actions SET action_type = 'diplomatic' WHERE action_type = 'diplomatic_policy';")
    op.execute(
        """
        UPDATE government_actions 
        SET action_type = 'unknown_legacy' 
        WHERE action_type NOT IN ('diplomatic', 'regulatory', 'legislative', 'judicial', 'administrative', 'fiscal', 'security');
        """
    )
    op.execute("UPDATE government_actions SET validation_source = 'legacy_import' WHERE validation_source IS NOT NULL AND validation_source NOT IN ('groq', 'gemini', 'rules', 'legacy_import');")
    op.execute("UPDATE government_actions SET brief_source = 'legacy_unverified' WHERE brief_source IS NOT NULL AND brief_source NOT IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none');")

    ga_checks = _get_existing_check_constraints(conn, "government_actions")
    if "ck_government_actions_rank" not in ga_checks:
        op.create_check_constraint("ck_government_actions_rank", "government_actions", "rank BETWEEN 1 AND 10")
        record_provenance("constraint", "government_actions", "ck_government_actions_rank")
    if "ck_government_actions_action_type" not in ga_checks:
        op.create_check_constraint("ck_government_actions_action_type", "government_actions", "action_type IN ('diplomatic', 'regulatory', 'legislative', 'judicial', 'administrative', 'fiscal', 'security', 'unknown_legacy')")
        record_provenance("constraint", "government_actions", "ck_government_actions_action_type")
    if "ck_government_actions_confidence" not in ga_checks:
        op.create_check_constraint("ck_government_actions_confidence", "government_actions", "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)")
        record_provenance("constraint", "government_actions", "ck_government_actions_confidence")
    if "ck_government_actions_validation_source" not in ga_checks:
        op.create_check_constraint("ck_government_actions_validation_source", "government_actions", "validation_source IS NULL OR validation_source IN ('groq', 'gemini', 'rules', 'legacy_import')")
        record_provenance("constraint", "government_actions", "ck_government_actions_validation_source")
    if "ck_government_actions_brief_source" not in ga_checks:
        op.create_check_constraint("ck_government_actions_brief_source", "government_actions", "brief_source IS NULL OR brief_source IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none')")
        record_provenance("constraint", "government_actions", "ck_government_actions_brief_source")

    # 7. protests drift reconciliation, geography overhaul & check constraints
    pr_cols = _get_existing_column_names(conn, "protests")
    for col_name, col_type, nullable, default in [
        ("story_id", sa.BigInteger(), True, None),
        ("location_name", sa.String(length=128), True, None),
        ("location_level", sa.String(length=32), False, "city"),
        ("state", sa.String(length=128), True, None),
        ("country_code", sa.String(length=3), False, "IND"),
        ("llm_brief", sa.Text(), True, None),
        ("validation_source", sa.String(length=32), True, None),
        ("brief_source", sa.String(length=32), True, "none"),
        ("confidence", sa.Numeric(4, 3), True, None),
    ]:
        if col_name not in pr_cols:
            op.add_column("protests", sa.Column(col_name, col_type, server_default=default, nullable=nullable))
            record_provenance("column", "protests", col_name)
        elif col_name == "validation_source":
            op.alter_column("protests", "validation_source", existing_type=sa.String(10), type_=sa.String(32))

    # Make city nullable in protests
    op.alter_column("protests", "city", existing_type=sa.String(length=128), nullable=True)

    # Backfill protest geography for legacy rows
    op.execute("UPDATE protests SET location_name = city, location_level = 'national', city = NULL WHERE city = 'India (National)';")
    op.execute("UPDATE protests SET location_name = city, location_level = 'state', state = TRIM(REPLACE(city, '(Regional)', '')), city = NULL WHERE city LIKE '%(Regional)';")
    op.execute("UPDATE protests SET location_name = city, location_level = 'city' WHERE location_name IS NULL AND city IS NOT NULL;")

    # Normalize existing legacy values
    op.execute("UPDATE protests SET validation_source = 'legacy_import' WHERE validation_source IS NOT NULL AND validation_source NOT IN ('groq', 'gemini', 'rules', 'legacy_import');")
    op.execute("UPDATE protests SET brief_source = 'legacy_unverified' WHERE brief_source IS NOT NULL AND brief_source NOT IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none');")
    op.execute("UPDATE protests SET location_level = 'unknown' WHERE location_level IS NOT NULL AND location_level NOT IN ('venue', 'city', 'district', 'state', 'national', 'unknown');")

    pr_checks = _get_existing_check_constraints(conn, "protests")
    if "ck_protests_severity" not in pr_checks:
        op.create_check_constraint("ck_protests_severity", "protests", "event_severity IS NULL OR (event_severity >= 0.0 AND event_severity <= 100.0)")
        record_provenance("constraint", "protests", "ck_protests_severity")
    if "ck_protests_location_level" not in pr_checks:
        op.create_check_constraint("ck_protests_location_level", "protests", "location_level IN ('venue', 'city', 'district', 'state', 'national', 'unknown')")
        record_provenance("constraint", "protests", "ck_protests_location_level")
    if "ck_protests_confidence" not in pr_checks:
        op.create_check_constraint("ck_protests_confidence", "protests", "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)")
        record_provenance("constraint", "protests", "ck_protests_confidence")
    if "ck_protests_validation_source" not in pr_checks:
        op.create_check_constraint("ck_protests_validation_source", "protests", "validation_source IS NULL OR validation_source IN ('groq', 'gemini', 'rules', 'legacy_import')")
        record_provenance("constraint", "protests", "ck_protests_validation_source")
    if "ck_protests_brief_source" not in pr_checks:
        op.create_check_constraint("ck_protests_brief_source", "protests", "brief_source IS NULL OR brief_source IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none')")
        record_provenance("constraint", "protests", "ck_protests_brief_source")

    # 8. commodity_news drift reconciliation & check constraints
    cn_cols = _get_existing_column_names(conn, "commodity_news")
    for col_name, col_type, nullable, default in [
        ("story_id", sa.BigInteger(), True, None),
        ("llm_brief", sa.Text(), True, None),
        ("validation_source", sa.String(length=32), True, None),
        ("brief_source", sa.String(length=32), True, "none"),
        ("confidence", sa.Numeric(4, 3), True, None),
        ("relevance_reason", sa.Text(), True, None),
        ("expires_at", sa.DateTime(timezone=True), True, None),
    ]:
        if col_name not in cn_cols:
            op.add_column("commodity_news", sa.Column(col_name, col_type, server_default=default, nullable=nullable))
            record_provenance("column", "commodity_news", col_name)
        elif col_name == "validation_source":
            op.alter_column("commodity_news", "validation_source", existing_type=sa.String(10), type_=sa.String(32))

    op.execute("UPDATE commodity_news SET validation_source = 'legacy_import' WHERE validation_source IS NOT NULL AND validation_source NOT IN ('groq', 'gemini', 'rules', 'legacy_import');")
    op.execute("UPDATE commodity_news SET brief_source = 'legacy_unverified' WHERE brief_source IS NOT NULL AND brief_source NOT IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none');")

    cn_checks = _get_existing_check_constraints(conn, "commodity_news")
    if "ck_commodity_news_rank" not in cn_checks:
        op.create_check_constraint("ck_commodity_news_rank", "commodity_news", "rank > 0")
        record_provenance("constraint", "commodity_news", "ck_commodity_news_rank")
    if "ck_commodity_news_confidence" not in cn_checks:
        op.create_check_constraint("ck_commodity_news_confidence", "commodity_news", "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)")
        record_provenance("constraint", "commodity_news", "ck_commodity_news_confidence")
    if "ck_commodity_news_validation_source" not in cn_checks:
        op.create_check_constraint("ck_commodity_news_validation_source", "commodity_news", "validation_source IS NULL OR validation_source IN ('groq', 'gemini', 'rules', 'legacy_import')")
        record_provenance("constraint", "commodity_news", "ck_commodity_news_validation_source")
    if "ck_commodity_news_brief_source" not in cn_checks:
        op.create_check_constraint("ck_commodity_news_brief_source", "commodity_news", "brief_source IS NULL OR brief_source IN ('llm_grounded', 'template_fallback', 'legacy_unverified', 'none')")
        record_provenance("constraint", "commodity_news", "ck_commodity_news_brief_source")

    # 9. chokepoints canonical status & check constraints
    chk_cols = _get_existing_column_names(conn, "chokepoints")
    for col_name, col_type, nullable, default in [
        ("expires_at", sa.DateTime(timezone=True), True, None),
        ("last_seen_at", sa.DateTime(timezone=True), True, None),
    ]:
        if col_name not in chk_cols:
            op.add_column("chokepoints", sa.Column(col_name, col_type, server_default=default, nullable=nullable))
            record_provenance("column", "chokepoints", col_name)

    # Migrate legacy chokepoint status values to green / yellow / red
    op.execute("UPDATE chokepoints SET status = 'green' WHERE status = 'nominal';")
    op.execute("UPDATE chokepoints SET status = 'yellow' WHERE status = 'elevated';")
    op.execute("UPDATE chokepoints SET status = 'red' WHERE status = 'critical';")

    chk_checks = _get_existing_check_constraints(conn, "chokepoints")
    if "ck_chokepoints_status" not in chk_checks:
        op.create_check_constraint("ck_chokepoints_status", "chokepoints", "status IN ('green', 'yellow', 'red')")
        record_provenance("constraint", "chokepoints", "ck_chokepoints_status")
    if "ck_chokepoints_disruption_score" not in chk_checks:
        op.create_check_constraint("ck_chokepoints_disruption_score", "chokepoints", "disruption_score IS NULL OR (disruption_score >= 0.0 AND disruption_score <= 100.0)")
        record_provenance("constraint", "chokepoints", "ck_chokepoints_disruption_score")

    # 10. article_text_cache canonical URL & retry metadata
    ac_cols = _get_existing_column_names(conn, "article_text_cache")
    for col_name, col_type, nullable, default in [
        ("canonical_url", sa.Text(), True, None),
        ("title", sa.Text(), True, None),
        ("http_status", sa.Integer(), True, None),
        ("attempt_count", sa.Integer(), False, "0"),
        ("last_error", sa.Text(), True, None),
        ("next_retry_at", sa.DateTime(timezone=True), True, None),
        ("last_success_at", sa.DateTime(timezone=True), True, None),
        ("updated_at", sa.DateTime(timezone=True), False, sa.func.now()),
    ]:
        if col_name not in ac_cols:
            op.add_column("article_text_cache", sa.Column(col_name, col_type, server_default=default, nullable=nullable))
            record_provenance("column", "article_text_cache", col_name)

    # Backfill canonical_url from source_url (strip query string and fragment)
    op.execute(
        """
        UPDATE article_text_cache
        SET canonical_url = LOWER(SPLIT_PART(SPLIT_PART(source_url, '?', 1), '#', 1))
        WHERE canonical_url IS NULL;
        """
    )
    # Deterministic ctid-based deduplication prioritizing successful text records
    op.execute(
        """
        WITH ranked_articles AS (
            SELECT ctid,
                   ROW_NUMBER() OVER (
                       PARTITION BY canonical_url
                       ORDER BY 
                           CASE WHEN fetch_status = 'success' AND article_text IS NOT NULL AND LENGTH(article_text) > 0 THEN 1 ELSE 2 END ASC,
                           LENGTH(COALESCE(article_text, '')) DESC,
                           fetched_at DESC NULLS LAST,
                           ctid DESC
                   ) AS rnum
            FROM article_text_cache
        )
        DELETE FROM article_text_cache
        WHERE ctid IN (SELECT ctid FROM ranked_articles WHERE rnum > 1);
        """
    )
    # Enforce NOT NULL on canonical_url now that backfill and deduplication have succeeded
    op.alter_column("article_text_cache", "canonical_url", existing_type=sa.Text(), nullable=False)
    inspector = sa.inspect(conn)
    existing_ac_idxs = {idx["name"] for idx in inspector.get_indexes("article_text_cache")}
    if "ix_article_text_cache_canonical_url" not in existing_ac_idxs:
        op.create_index("ix_article_text_cache_canonical_url", "article_text_cache", ["canonical_url"], unique=True)
        record_provenance("index", "article_text_cache", "ix_article_text_cache_canonical_url")


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_table_names(conn)

    if "_migration_0008_provenance" not in tables:
        return

    provenance_rows = conn.execute(sa.text("SELECT object_type, table_name, object_name FROM _migration_0008_provenance;")).fetchall()
    added_cols = {(tbl, obj) for (obj_type, tbl, obj) in provenance_rows if obj_type == "column"}
    added_checks = {(tbl, obj) for (obj_type, tbl, obj) in provenance_rows if obj_type == "constraint"}
    added_idxs = {(tbl, obj) for (obj_type, tbl, obj) in provenance_rows if obj_type == "index"}
    added_tbls = {obj for (obj_type, tbl, obj) in provenance_rows if obj_type == "table"}

    # 1. Drop constraints added by 0008
    for tbl, chk_name in added_checks:
        if tbl in _get_existing_table_names(conn):
            if chk_name in _get_existing_check_constraints(conn, tbl):
                op.drop_constraint(chk_name, table_name=tbl, type_="check")

    # 2. Drop indexes added by 0008
    for tbl, idx_name in added_idxs:
        if tbl in _get_existing_table_names(conn):
            inspector = sa.inspect(conn)
            if idx_name in {idx["name"] for idx in inspector.get_indexes(tbl)}:
                op.drop_index(idx_name, table_name=tbl)

    # 3. Drop referencing FK columns on other tables first
    fk_referencing_cols = [
        ("cascade_scores", "run_id"),
        ("regional_headlines", "story_id"),
        ("government_actions", "story_id"),
        ("protests", "story_id"),
        ("commodity_news", "story_id"),
    ]
    for tbl, col in fk_referencing_cols:
        if (tbl, col) in added_cols and tbl in _get_existing_table_names(conn):
            if col in _get_existing_column_names(conn, tbl):
                op.drop_column(tbl, col)

    # 4. Drop child tables before parent tables
    for child_tbl in ["chokepoint_events", "cascade_scores"]:
        if child_tbl in added_tbls and child_tbl in _get_existing_table_names(conn):
            op.drop_table(child_tbl)

    # 5. Drop parent tables
    for parent_tbl in ["cascade_runs", "news_stories"]:
        if parent_tbl in added_tbls and parent_tbl in _get_existing_table_names(conn):
            op.drop_table(parent_tbl)

    # 6. Revert city nullability if protests exists (before dropping columns)
    if "protests" in _get_existing_table_names(conn):
        cols = _get_existing_column_names(conn, "protests")
        if "city" in cols:
            if "location_name" in cols:
                op.execute("UPDATE protests SET city = COALESCE(location_name, 'Unknown') WHERE city IS NULL;")
            else:
                op.execute("UPDATE protests SET city = 'Unknown' WHERE city IS NULL;")
            op.alter_column("protests", "city", existing_type=sa.String(length=128), nullable=False)

    # 7. Drop remaining columns added by 0008
    for tbl, col in added_cols:
        if (tbl, col) not in fk_referencing_cols and tbl in _get_existing_table_names(conn):
            if col in _get_existing_column_names(conn, tbl):
                op.drop_column(tbl, col)

    # 8. Drop provenance table
    if "_migration_0008_provenance" in _get_existing_table_names(conn):
        op.drop_table("_migration_0008_provenance")
