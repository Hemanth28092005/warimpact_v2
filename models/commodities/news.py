"""Commodity News Ingestion Pipeline.

Extracts page titles from GDELT event URLs matching the top 30 tracked commodities.
Upserts into commodity_news table on (commodity_code, rank).
"""

import logging
from typing import Any
import psycopg

from ingestion.dashboard import headline_extractor

logger = logging.getLogger(__name__)

DB_URL = "user=war_impact password=war_impact_password dbname=war_impact host=localhost port=5432"


def update_commodity_news(max_rank: int = 5) -> dict[str, Any]:
    """Ingest top headlines for all 30 tracked commodities."""
    logger.info("Starting commodity news matching pipeline...")
    records_updated = 0

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT commodity_code, name, category FROM tracked_commodities;")
            commodities = cur.fetchall()

            for code, name, category in commodities:
                # Query GDELT events matching keywords in source_url or themes
                keyword_query = f"%{name.split()[0].lower()}%"
                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, num_mentions
                    FROM gdelt_events
                    WHERE (LOWER(source_url) LIKE %s OR LOWER(source_url) LIKE %s)
                      AND source_url IS NOT NULL AND source_url != ''
                      AND event_date >= CURRENT_DATE - INTERVAL '14 days'
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 15;
                    """,
                    (keyword_query, f"%{category.lower()}%"),
                )
                candidates = cur.fetchall()

                rank = 1
                for ev_id, url, ev_date, mentions in candidates:
                    if rank > max_rank:
                        break

                    headline = headline_extractor.extract_page_title(url)
                    if not headline or len(headline) < 10:
                        headline = f"Market & Supply Telemetry Update for {name} ({code})"

                    cur.execute(
                        """
                        INSERT INTO commodity_news (commodity_code, rank, headline, gdelt_event_id, source_url, published_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (commodity_code, rank) DO UPDATE
                        SET headline = EXCLUDED.headline,
                            gdelt_event_id = EXCLUDED.gdelt_event_id,
                            source_url = EXCLUDED.source_url,
                            published_at = EXCLUDED.published_at,
                            updated_at = NOW();
                        """,
                        (code, rank, headline, ev_id, url, ev_date),
                    )
                    records_updated += 1
                    rank += 1

                if rank == 1:
                    logger.warning(f"No commodity news matches for {code} ({name}); existing rows preserved.")

        conn.commit()

    return {"commodity_news_updated": records_updated}
