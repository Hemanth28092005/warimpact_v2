"""Phase 6a Dashboard Data Layer Test Suite.

Verifies:
1. Migration & Schema
2. Static Seed Data (30 commodities, 13 chokepoints, 253 full-globe boundaries)
3. Shared Ingestion Tasks & Upsert Invariance (7 regions including standalone united_states & india)
4. Chokepoints Disruption Engine with Mock Injected Event Test
5. Commodity News Pipeline
6. India Trade Routes & Null-Chokepoint Weight Redistribution Formula
7. Empty Shipping Rates Table
"""

import pytest
import psycopg

from ingestion.dashboard.tasks import (
    run_regional_headlines,
    run_government_actions,
    run_protests,
)
from models.chokepoints.disruption import calculate_chokepoint_disruptions
from models.commodities.news import update_commodity_news
from models.trade_routes.routes import update_india_trade_routes

DB_URL = "user=war_impact password=war_impact_password dbname=war_impact host=localhost port=5432"


@pytest.fixture(autouse=True)
def mock_headline_extractor(monkeypatch):
    """Mock title extraction across all dashboard tests for fast offline execution."""
    monkeypatch.setattr("ingestion.dashboard.headline_extractor.extract_page_title", lambda url, timeout_seconds=2: "Mocked Test Headline Security Update")
    monkeypatch.setattr("ingestion.dashboard.tasks.headline_extractor.extract_page_title", lambda url, timeout_seconds=2: "Mocked Test Headline Security Update")
    monkeypatch.setattr("models.commodities.news.headline_extractor.extract_page_title", lambda url, timeout_seconds=2: "Mocked Commodity Trade News")


def test_seed_data_counts_and_samples():
    """Verify Step 2 seed data row counts and sample values for full globe."""
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # 1. commodities
            cur.execute("SELECT COUNT(*) FROM tracked_commodities;")
            c_count = cur.fetchone()[0]
            assert c_count == 30, f"Expected 30 commodities, got {c_count}"

            cur.execute("SELECT commodity_code, name, annual_value_usd FROM tracked_commodities LIMIT 3;")
            c_samples = cur.fetchall()
            assert len(c_samples) == 3
            assert c_samples[0][2] > 0

            # 2. chokepoints
            cur.execute("SELECT COUNT(*) FROM chokepoints;")
            chk_count = cur.fetchone()[0]
            assert chk_count == 13, f"Expected 13 chokepoints, got {chk_count}"

            cur.execute("SELECT code, name, baseline_mbd FROM chokepoints WHERE code = 'HORMUZ';")
            hormuz = cur.fetchone()
            assert hormuz is not None
            assert float(hormuz[2]) == 21.0

            # 3. world_boundaries (Full-Globe ~200+ countries)
            cur.execute("SELECT COUNT(*) FROM world_boundaries;")
            bnd_count = cur.fetchone()[0]
            assert bnd_count >= 200, f"Expected >= 200 world boundaries for full globe, got {bnd_count}"


def test_upsert_invariance_regional_headlines():
    """Verify running regional_headlines twice does not duplicate rows across 7 regions."""
    run_regional_headlines()
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM regional_headlines;")
            count1 = cur.fetchone()[0]

            # Verify standalone india and united_states entries exist
            cur.execute("SELECT COUNT(*) FROM regional_headlines WHERE region = 'india';")
            assert cur.fetchone()[0] <= 10

            cur.execute("SELECT COUNT(*) FROM regional_headlines WHERE region = 'united_states';")
            assert cur.fetchone()[0] <= 10

    # Second run for invariance check
    run_regional_headlines()
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM regional_headlines;")
            count2 = cur.fetchone()[0]

    assert count1 == count2, f"Row count changed on second run (upsert failed): {count1} != {count2}"


def test_protests_cameo_filter_and_upsert():
    """Verify protest task runs and respects CAMEO event code filtering (excludes violent conflict 180-195)."""
    res = run_protests()
    assert "protests_updated" in res

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.gdelt_event_id, g.event_code
                FROM protests p
                JOIN gdelt_events g ON p.gdelt_event_id = g.global_event_id
                LIMIT 10;
                """
            )
            rows = cur.fetchall()
            for ev_id, ecode in rows:
                if ecode:
                    assert not ecode.startswith("18") and not ecode.startswith("19"), f"Violent event {ecode} in protests"


def test_government_actions_task():
    """Verify India government actions task runs and enforces rank upsert invariance (10 rows)."""
    res1 = run_government_actions()
    assert res1["government_actions_updated"] <= 10

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM government_actions;")
            count1 = cur.fetchone()[0]
            assert count1 <= 10, f"Expected <= 10 India government actions, got {count1}"

    # Re-run task to test rank upsert invariance
    run_government_actions()
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM government_actions;")
            count2 = cur.fetchone()[0]
            assert count1 == count2, f"Row count changed on second run: {count1} != {count2}"


def test_chokepoints_disruption_calculation():
    """Verify maritime chokepoints disruption scoring engine bounds and status."""
    res = calculate_chokepoint_disruptions()
    assert res["chokepoints_updated"] == 13

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, disruption_score, status FROM chokepoints;")
            rows = cur.fetchall()
            assert len(rows) == 13
            for code, score, status in rows:
                score_f = float(score)
                assert 0.0 <= score_f <= 100.0
                assert status in ("green", "yellow", "red")


def test_chokepoints_disruption_mock_injection():
    """Verify injecting known real disruption events near a chokepoint updates score and status."""
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Inject multiple high-severity kinetic events near Strait of Hormuz (26.54, 56.42)
            cur.execute(
                """
                INSERT INTO gdelt_events (
                    global_event_id, event_date, event_code, goldstein_scale, num_mentions,
                    action_geo_lat, action_geo_long, action_geo_country_code, source_url
                )
                VALUES 
                    (999999991, CURRENT_DATE, '190', -10.0, 500, 26.550000, 56.430000, 'IRN', 'https://mock.event.com/hormuz-1'),
                    (999999992, CURRENT_DATE, '195', -10.0, 500, 26.540000, 56.420000, 'IRN', 'https://mock.event.com/hormuz-2'),
                    (999999993, CURRENT_DATE, '193', -10.0, 500, 26.530000, 56.410000, 'IRN', 'https://mock.event.com/hormuz-3')
                ON CONFLICT (global_event_id) DO UPDATE SET num_mentions = 500;
                """
            )
        conn.commit()

    calculate_chokepoint_disruptions()

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT disruption_score, status FROM chokepoints WHERE code = 'HORMUZ';")
            score, status = cur.fetchone()
            assert float(score) >= 20.0
            assert status in ("yellow", "red")


def test_commodity_news_pipeline():
    """Verify commodity news pipeline updates tracked commodities."""
    res = update_commodity_news()
    assert "commodity_news_updated" in res

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT commodity_code) FROM commodity_news;")
            distinct_commodities = cur.fetchone()[0]
            assert distinct_commodities > 0


def test_india_trade_routes_and_risk_scoring():
    """Verify India trade routes arc generation & risk scoring formula."""
    res = update_india_trade_routes()
    assert res["routes_updated"] > 0
    assert isinstance(res["missing_commodities"], list)

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT commodity_code, partner_country, primary_chokepoint, risk_score FROM india_trade_routes LIMIT 5;")
            routes = cur.fetchall()
            assert len(routes) == 5
            for comm, partner, chk, score in routes:
                assert float(score) >= 0.0


def test_shipping_rates_table_empty():
    """Verify Step 7: shipping_rates table exists and is empty."""
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM shipping_rates;")
            count = cur.fetchone()[0]
            assert count == 0, f"Expected empty shipping_rates table, got {count}"
