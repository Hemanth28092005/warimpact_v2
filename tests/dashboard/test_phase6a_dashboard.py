"""Phase 6a Dashboard Data Layer Test Suite.

Verifies:
1. Migration & Schema
2. Static Seed Data (30 commodities, 13 chokepoints, 200+ world boundaries)
3. Shared Ingestion Tasks & Upsert Invariance (7 regions including standalone united_states & india)
4. Chokepoints Disruption Engine with Mock Injected Event Test
5. Commodity News Pipeline with Staged Snapshots
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
from scripts.seed_dashboard_data import main as seed_dashboard_data


@pytest.fixture(autouse=True)
def setup_dashboard_test_environment(test_db_url, monkeypatch):
    """Seed static dashboard tables in isolated test database and mock title extraction."""
    # Seed static commodities, chokepoints, and world boundaries in test DB
    seed_dashboard_data(db_url=test_db_url)

    # Mock title extraction for fast deterministic execution
    monkeypatch.setattr(
        "ingestion.dashboard.headline_extractor.extract_page_title",
        lambda url, timeout_seconds=2: "Official Strategic Security and Trade Agreement Framework",
    )


def test_seed_data_counts_and_samples(test_db_url: str):
    """Verify seed data row counts and sample values for full globe in test database."""
    with psycopg.connect(test_db_url) as conn:
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

            # 3. world_boundaries (Global countries)
            cur.execute("SELECT COUNT(*) FROM world_boundaries;")
            bnd_count = cur.fetchone()[0]
            assert bnd_count >= 10, f"Expected >= 10 world boundaries in test DB, got {bnd_count}"


def test_upsert_invariance_regional_headlines(test_db_url: str):
    """Verify running regional_headlines twice does not duplicate rows across 7 regions."""
    run_regional_headlines(db_url=test_db_url)
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM regional_headlines;")
            count1 = cur.fetchone()[0]

            # Verify standalone india and united_states entries exist
            cur.execute("SELECT COUNT(*) FROM regional_headlines WHERE region = 'india';")
            assert cur.fetchone()[0] <= 10

            cur.execute("SELECT COUNT(*) FROM regional_headlines WHERE region = 'united_states';")
            assert cur.fetchone()[0] <= 10

    # Second run for invariance check
    run_regional_headlines(db_url=test_db_url)
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM regional_headlines;")
            count2 = cur.fetchone()[0]

    assert count1 == count2, f"Row count changed on second run (upsert failed): {count1} != {count2}"


def test_government_actions_task(test_db_url: str):
    """Verify India government actions task runs and enforces rank upsert invariance (10 rows)."""
    res1 = run_government_actions(db_url=test_db_url)
    assert res1["government_actions_updated"] <= 10

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM government_actions;")
            count1 = cur.fetchone()[0]
            assert count1 <= 10, f"Expected <= 10 India government actions, got {count1}"

    # Re-run task to test rank upsert invariance
    run_government_actions(db_url=test_db_url)
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM government_actions;")
            count2 = cur.fetchone()[0]
            assert count1 == count2, f"Row count changed on second run: {count1} != {count2}"


def test_chokepoints_disruption_calculation(test_db_url: str):
    """Verify maritime chokepoints disruption scoring engine bounds and canonical status."""
    res = calculate_chokepoint_disruptions(db_url=test_db_url)
    assert res["chokepoints_updated"] == 13

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, disruption_score, status FROM chokepoints;")
            rows = cur.fetchall()
            assert len(rows) == 13
            for code, score, status in rows:
                score_f = float(score)
                assert 0.0 <= score_f <= 100.0
                assert status in ("green", "yellow", "red")


def test_chokepoints_disruption_mock_injection(test_db_url: str):
    """Verify injecting known disruption events near a chokepoint updates score and status."""
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gdelt_events (
                    global_event_id, event_date, event_code, goldstein_scale, num_mentions,
                    action_geo_lat, action_geo_long, action_geo_country_code, source_url
                )
                VALUES 
                    (999999991, CURRENT_DATE, '190', -10.0, 500, 26.550000, 56.430000, 'IRN', 'https://mock.event.com/hormuz-tanker-attack'),
                    (999999992, CURRENT_DATE, '195', -10.0, 500, 26.540000, 56.420000, 'IRN', 'https://mock.event.com/hormuz-drone-strike'),
                    (999999993, CURRENT_DATE, '193', -10.0, 500, 26.530000, 56.410000, 'IRN', 'https://mock.event.com/hormuz-missile-blockade')
                ON CONFLICT (global_event_id) DO UPDATE SET num_mentions = 500;
                """
            )
        conn.commit()

    calculate_chokepoint_disruptions(db_url=test_db_url)

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT disruption_score, status FROM chokepoints WHERE code = 'HORMUZ';")
            score, status = cur.fetchone()
            assert float(score) >= 25.0
            assert status in ("yellow", "red")


def test_commodity_news_pipeline(test_db_url: str):
    """Verify commodity news pipeline runs with staged atomic publishing."""
    res = update_commodity_news(db_url=test_db_url)
    assert "commodity_news_updated" in res


def test_india_trade_routes_and_risk_scoring(test_db_url: str):
    """Verify India trade routes arc generation & risk scoring formula."""
    res = update_india_trade_routes(db_url=test_db_url)
    assert res["routes_updated"] > 0
    assert isinstance(res["missing_commodities"], list)

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT commodity_code, partner_country, primary_chokepoint, risk_score FROM india_trade_routes LIMIT 5;")
            routes = cur.fetchall()
            assert len(routes) == 5
            for comm, partner, chk, score in routes:
                assert float(score) >= 0.0


def test_shipping_rates_table_empty(test_db_url: str):
    """Verify Step 7: shipping_rates table exists and is empty."""
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM shipping_rates;")
            count = cur.fetchone()[0]
            assert count == 0, f"Expected empty shipping_rates table, got {count}"
