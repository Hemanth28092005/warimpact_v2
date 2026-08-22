"""Isolated Alembic Migration Tests.

Strictly runs against 'war_impact_test' isolated database:
1. Tests clean upgrade from 0001 through 0008 (upgrade head).
2. Tests schema verification for all new tables and columns.
3. Tests downgrade to 0007 and re-upgrade to 0008.
4. Tests drifted schema reconciliation (idempotent upgrade when columns pre-exist).
"""

import os
from alembic.config import Config
from alembic import command
import psycopg
import pytest
from tests.conftest import validate_test_db_target


@pytest.fixture(autouse=True)
def ensure_test_database(test_db_url):
    """Ensure tests run strictly against test database URL."""
    validate_test_db_target(test_db_url)
    os.environ["DATABASE_URL"] = test_db_url.replace("postgresql://", "postgresql+psycopg://")


def _reset_test_database(test_db_url: str):
    """Drop and recreate public schema on test database."""
    validate_test_db_target(test_db_url)
    with psycopg.connect(test_db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE;")
            cur.execute("CREATE SCHEMA public;")


def test_clean_alembic_upgrade_and_downgrade(test_db_url: str):
    """Verify clean database migrates 0001 -> 0008, downgrades to 0007, and re-upgrades to 0008."""
    _reset_test_database(test_db_url)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url.replace("postgresql://", "postgresql+psycopg://"))

    # Upgrade to head (0008)
    command.upgrade(alembic_cfg, "head")

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            # Verify new tables exist
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
                """
            )
            tables = {r[0] for r in cur.fetchall()}
            assert "news_stories" in tables
            assert "chokepoint_events" in tables
            assert "cascade_runs" in tables
            assert "cascade_scores" in tables
            assert "regional_headlines" in tables
            assert "government_actions" in tables
            assert "protests" in tables
            assert "commodity_news" in tables
            assert "chokepoints" in tables
            assert "article_text_cache" in tables

            # Verify columns on news_stories
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'news_stories';"
            )
            ns_cols = {r[0] for r in cur.fetchall()}
            assert {"id", "canonical_url", "content_hash", "normalized_title", "source_domain"}.issubset(ns_cols)

            # Verify columns on chokepoint_events
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'chokepoint_events';"
            )
            ce_cols = {r[0] for r in cur.fetchall()}
            assert {"id", "chokepoint_code", "distance_km", "contribution_score", "reason", "observed_at"}.issubset(ce_cols)

            # Verify columns on cascade_runs
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'cascade_runs';"
            )
            cr_cols = {r[0] for r in cur.fetchall()}
            assert {"run_id", "started_at", "calculation_status", "cii_max_score_date", "window_days"}.issubset(cr_cols)

    # Downgrade to 0007
    command.downgrade(alembic_cfg, "20260804_0007")

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            tables = {r[0] for r in cur.fetchall()}
            assert "news_stories" not in tables
            assert "chokepoint_events" not in tables
            assert "cascade_runs" not in tables

    # Re-upgrade to head (0008)
    command.upgrade(alembic_cfg, "head")

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            tables = {r[0] for r in cur.fetchall()}
            assert "news_stories" in tables
            assert "chokepoint_events" in tables


def test_drifted_schema_upgrade_reconciliation(test_db_url: str):
    """Verify migration 0008 succeeds when run on a drifted database with pre-existing partial columns."""
    _reset_test_database(test_db_url)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url.replace("postgresql://", "postgresql+psycopg://"))

    # First upgrade up to 0007
    command.upgrade(alembic_cfg, "20260804_0007")

    # Manually simulate schema drift on the 0007 tables
    with psycopg.connect(test_db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE regional_headlines ADD COLUMN IF NOT EXISTS llm_brief TEXT;")
            cur.execute("ALTER TABLE regional_headlines ADD COLUMN IF NOT EXISTS validation_source VARCHAR(10);")
            cur.execute("ALTER TABLE government_actions ADD COLUMN IF NOT EXISTS llm_brief TEXT;")
            cur.execute("ALTER TABLE government_actions ADD COLUMN IF NOT EXISTS validation_source VARCHAR(10);")
            cur.execute("ALTER TABLE protests ADD COLUMN IF NOT EXISTS llm_brief TEXT;")
            cur.execute("ALTER TABLE protests ADD COLUMN IF NOT EXISTS validation_source VARCHAR(10);")

    # Now run upgrade to 0008 - must not fail on duplicate column errors
    command.upgrade(alembic_cfg, "head")

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'regional_headlines';")
            cols = {r[0] for r in cur.fetchall()}
            assert {"story_id", "llm_brief", "validation_source", "brief_source", "confidence"}.issubset(cols)
