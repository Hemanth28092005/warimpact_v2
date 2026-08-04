"""Dedicated live escalation article fetcher for high-severity regional GDELT events.

Processes newly ingested GDELT batches, filters for target regions and severe conflict events (severity <= -0.5),
and fetches uncached article text into article_text_cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.sentiment.article_fetcher import fetch_and_cache_articles
from models.sentiment.scorer import compute_composite_historical_sentiment

logger = get_logger(__name__)

REGION_COUNTRY_MAPPING: dict[str, list[str]] = {
    "india": ["IND"],
    "usa": ["USA"],
    "europe": ["GBR", "FRA", "DEU", "ITA", "ESP", "UKR"],
    "middle_east": ["ISR", "TUR", "SAU", "SYR", "YEM"],
}

ALL_TARGET_COUNTRIES: list[str] = sorted(
    list({cc for country_list in REGION_COUNTRY_MAPPING.values() for cc in country_list})
)


@dataclass(frozen=True)
class EscalationFetchSummary:
    lookback_minutes: int
    matched_events_count: int
    unique_urls_count: int
    cache_hits_count: int
    new_fetches_attempted: int
    successful_fetches: int


async def fetch_escalation_article_text(
    lookback_minutes: int = 20,
    conn: AsyncConnection | None = None,
) -> EscalationFetchSummary:
    """Fetch uncached article text for newly ingested severe conflict events across target regions.

    Args:
        lookback_minutes: Number of trailing minutes to query ingested events (default 20m for 15m cadence).
        conn: Optional DB connection.
    """
    logger.info("escalation_article_fetch_started", extra={"lookback_minutes": lookback_minutes})

    async def _execute(c: AsyncConnection) -> EscalationFetchSummary:
        async with c.cursor() as cur:
            # Query newly ingested events in target countries within lookback window
            await cur.execute(
                """
                SELECT global_event_id, source_url, avg_tone, goldstein_scale, quad_class,
                       action_geo_country_code, actor1_country_code, actor2_country_code
                FROM gdelt_events
                WHERE event_date >= (SELECT COALESCE(MAX(event_date), CURRENT_DATE) FROM gdelt_events) - (%s || ' minutes')::INTERVAL
                  AND (
                    action_geo_country_code = ANY(%s)
                    OR actor1_country_code = ANY(%s)
                    OR actor2_country_code = ANY(%s)
                  )
                  AND source_url IS NOT NULL
                  AND source_url != ''
                ORDER BY event_date DESC, num_mentions DESC
                LIMIT 200
                """,
                (str(lookback_minutes), ALL_TARGET_COUNTRIES, ALL_TARGET_COUNTRIES, ALL_TARGET_COUNTRIES),
            )
            rows = await cur.fetchall()

        matched_events = []
        for r in rows:
            avg_tone = float(r[2]) if r[2] is not None else None
            goldstein = float(r[3]) if r[3] is not None else None
            quad_class = int(r[4]) if r[4] is not None else None
            severity = compute_composite_historical_sentiment(avg_tone, goldstein, quad_class)

            if severity <= -0.5:
                matched_events.append({"global_event_id": r[0], "source_url": r[1], "severity": severity})

        unique_urls = list({e["source_url"] for e in matched_events})

        if not unique_urls:
            summary = EscalationFetchSummary(
                lookback_minutes=lookback_minutes,
                matched_events_count=len(matched_events),
                unique_urls_count=0,
                cache_hits_count=0,
                new_fetches_attempted=0,
                successful_fetches=0,
            )
            logger.info("escalation_article_fetch_completed", extra=summary.__dict__)
            return summary

        # Check existing cache
        async with c.cursor() as cur:
            await cur.execute(
                """
                SELECT source_url
                FROM article_text_cache
                WHERE source_url = ANY(%s)
                """,
                (unique_urls,),
            )
            cached_rows = await cur.fetchall()
            cached_urls = {r[0] for r in cached_rows}

        uncached_urls = [u for u in unique_urls if u not in cached_urls]
        cache_hits = len(unique_urls) - len(uncached_urls)

        fetched_map = {}
        if uncached_urls:
            fetched_map = await fetch_and_cache_articles(c, uncached_urls)

        successful_fetches = sum(1 for status in fetched_map.values() if status == "success")

        summary = EscalationFetchSummary(
            lookback_minutes=lookback_minutes,
            matched_events_count=len(matched_events),
            unique_urls_count=len(unique_urls),
            cache_hits_count=cache_hits,
            new_fetches_attempted=len(uncached_urls),
            successful_fetches=successful_fetches,
        )
        logger.info("escalation_article_fetch_completed", extra=summary.__dict__)
        return summary

    if conn is not None:
        return await _execute(conn)
    else:
        async with open_async_connection() as conn_obj:
            return await _execute(conn_obj)
