"""Shared Parameterized Celery Ingestion Tasks for Phase 6a Dashboard Data Layer.

Implements single parameterized ingestion pattern for:
- regional_headlines (upsert on (region, rank))
- government_actions (upsert on (country_code, rank))
- protests (upsert on (city, event_date, headline), India-only)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from celery import shared_task  # type: ignore[import-untyped]

from ingestion.common.config import get_settings
from ingestion.dashboard import headline_extractor

logger = logging.getLogger(__name__)
settings = get_settings()

DB_URL = "user=war_impact password=war_impact_password dbname=war_impact host=localhost port=5432"

REGION_MAPPING = {
    "united_states": ["USA"],
    "india": ["IND"],
    "africa": ["SDN", "ETH", "SOM", "NGA", "ZAF"],
    "asia_pacific": ["CHN", "JPN", "KOR", "TWN", "IDN", "MYS", "PHL", "VNM", "MMR"],
    "middle_east": ["ISR", "IRN", "SAU", "TUR", "SYR", "IRQ", "YEM", "EGY"],
    "europe": ["RUS", "UKR", "DEU", "FRA", "GBR", "POL", "BLR"],
    "latin_america_australia": ["BRA", "MEX", "COL", "VEN", "AUS"],
}

GOVT_ACTION_CAMEO_PREFIXES = ("01", "02")  # CAMEO 010-025 Make public statement / Appeal
PROTEST_CAMEO_PREFIXES = ("14",)           # CAMEO 140-145 Engage in protest/demonstration


def ingest_gdelt_dashboard_feed(
    feed_type: str,
    filter_params: dict[str, Any],
    upsert_key: str,
    max_rank: int = 10,
) -> dict[str, Any]:
    """Single reusable task runner for dashboard feeds.
    
    Rule 4: Preserves existing rows if zero qualifying events found in a cycle.
    Rule 3: Title-only extraction.
    Rule 1: Fixed upsert key.
    """
    logger.info(f"Starting dashboard feed ingestion: feed_type={feed_type}, key={upsert_key}")
    records_updated = 0

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            if feed_type == "regional_headlines":
                region = filter_params["region"]
                countries = filter_params["countries"]
                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, num_mentions, avg_tone,
                           COALESCE(actor1_country_code, action_geo_country_code) AS country_code
                    FROM gdelt_events
                    WHERE (action_geo_country_code = ANY(%s) OR actor1_country_code = ANY(%s))
                      AND source_url IS NOT NULL AND source_url != ''
                      AND event_date >= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 30;
                    """,
                    (countries, countries),
                )
                candidates = cur.fetchall()

                rank = 1
                for ev_id, url, ev_date, mentions, tone, ccode in candidates:
                    if rank > max_rank:
                        break
                    headline = headline_extractor.extract_page_title(url)
                    if not headline or len(headline) < 10:
                        # Fallback to structured title if page title un-fetchable
                        headline = f"Security & Economic Telemetry Event in {ccode or region} (Event {ev_id})"

                    cur.execute(
                        """
                        INSERT INTO regional_headlines (region, rank, headline, gdelt_event_id, source_url, published_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (region, rank) DO UPDATE
                        SET headline = EXCLUDED.headline,
                            gdelt_event_id = EXCLUDED.gdelt_event_id,
                            source_url = EXCLUDED.source_url,
                            published_at = EXCLUDED.published_at,
                            updated_at = NOW();
                        """,
                        (region, rank, headline, ev_id, url, ev_date),
                    )
                    records_updated += 1
                    rank += 1

                if records_updated == 0:
                    logger.warning(f"No qualifying events found for region {region}; existing rows preserved.")

            elif feed_type == "government_actions":
                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, event_code, num_mentions
                    FROM gdelt_events
                    WHERE (action_geo_country_code = 'IN' OR actor1_country_code = 'IND')
                      AND (event_code LIKE '01%%' OR event_code LIKE '02%%')
                      AND source_url IS NOT NULL AND source_url != ''
                      AND event_date >= CURRENT_DATE - INTERVAL '14 days'
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 20;
                    """
                )
                candidates = cur.fetchall()

                rank = 1
                for ev_id, url, ev_date, ecode, mentions in candidates:
                    if rank > max_rank:
                        break
                    headline = headline_extractor.extract_page_title(url)
                    if not headline or len(headline) < 10:
                        headline = f"Government Policy Action ({ecode}) — India"

                    cur.execute(
                        """
                        INSERT INTO government_actions (rank, headline, action_type, gdelt_event_id, source_url, published_at, updated_at)
                        VALUES (%s, %s, 'diplomatic_policy', %s, %s, %s, NOW())
                        ON CONFLICT (rank) DO UPDATE
                        SET headline = EXCLUDED.headline,
                            action_type = EXCLUDED.action_type,
                            gdelt_event_id = EXCLUDED.gdelt_event_id,
                            source_url = EXCLUDED.source_url,
                            published_at = EXCLUDED.published_at,
                            updated_at = NOW();
                        """,
                        (rank, headline, ev_id, url, ev_date),
                    )
                    records_updated += 1
                    rank += 1

                if records_updated == 0:
                    logger.warning("No government actions found for India; existing rows preserved.")

            elif feed_type == "protests":
                # India-only protests
                # Clean up rows older than 30 days
                cur.execute("DELETE FROM protests WHERE event_date < CURRENT_DATE - INTERVAL '30 days';")

                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, action_geo_lat, action_geo_long, num_mentions, goldstein_scale
                    FROM gdelt_events
                    WHERE (action_geo_country_code = 'IND' OR action_geo_country_code = 'IN')
                      AND event_code LIKE '14%%'
                      AND event_code NOT LIKE '18%%' AND event_code NOT LIKE '19%%'
                      AND source_url IS NOT NULL AND source_url != ''
                      AND event_date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 25;
                    """
                )
                candidates = cur.fetchall()

                for ev_id, url, ev_date, lat, long_, mentions, goldstein in candidates:
                    headline = headline_extractor.extract_page_title(url)
                    if not headline or len(headline) < 10:
                        headline = f"Civil Protest / Unrest Demonstration in India (Event {ev_id})"

                    city = "India (Regional Unrest)"
                    severity = abs(float(goldstein or -5.0)) * 10.0

                    cur.execute(
                        """
                        INSERT INTO protests (city, event_date, headline, action_geo_lat, action_geo_long, gdelt_event_id, source_url, event_severity, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (city, event_date, headline) DO UPDATE
                        SET action_geo_lat = EXCLUDED.action_geo_lat,
                            action_geo_long = EXCLUDED.action_geo_long,
                            gdelt_event_id = EXCLUDED.gdelt_event_id,
                            source_url = EXCLUDED.source_url,
                            event_severity = EXCLUDED.event_severity,
                            updated_at = NOW();
                        """,
                        (city, ev_date, headline, lat, long_, ev_id, url, severity),
                    )
                    records_updated += 1

                if records_updated == 0:
                    logger.warning("No protest events found for India; existing rows preserved.")

        conn.commit()

    return {"feed_type": feed_type, "records_updated": records_updated}


@shared_task(name="ingestion.dashboard.tasks.run_regional_headlines")
def run_regional_headlines() -> dict[str, int]:
    """15-min scheduled task for regional_headlines."""
    total = 0
    for region, countries in REGION_MAPPING.items():
        res = ingest_gdelt_dashboard_feed(
            feed_type="regional_headlines",
            filter_params={"region": region, "countries": countries},
            upsert_key="region_rank",
            max_rank=10,
        )
        total += res["records_updated"]
    return {"total_regional_headlines_updated": total}


@shared_task(name="ingestion.dashboard.tasks.run_government_actions")
def run_government_actions() -> dict[str, int]:
    """15-min scheduled task for India government_actions (top 10 by rank)."""
    res = ingest_gdelt_dashboard_feed(
        feed_type="government_actions",
        filter_params={},
        upsert_key="rank",
        max_rank=10,
    )
    return {"government_actions_updated": res["records_updated"]}


@shared_task(name="ingestion.dashboard.tasks.run_protests")
def run_protests() -> dict[str, int]:
    """10-min scheduled task for India protests."""
    res = ingest_gdelt_dashboard_feed(
        feed_type="protests",
        filter_params={"country_code": "IND"},
        upsert_key="city_date_headline",
    )
    return {"protests_updated": res["records_updated"]}
