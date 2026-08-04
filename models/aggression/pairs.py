"""Bilateral country pair extraction and null-actor handling for gdelt_events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from psycopg import AsyncConnection

from ingestion.common.logger import get_logger
from models.aggression.cow_parser import TARGET_COUNTRIES
from models.aggression.scorer import EventScoringInput

logger = get_logger(__name__)


@dataclass(frozen=True)
class BilateralEventRecord:
    global_event_id: int
    event_date: date
    country_a: str
    country_b: str
    quad_class: int | None
    goldstein_scale: float | None
    avg_tone: float | None
    num_mentions: int | None
    num_sources: int | None
    num_articles: int | None


@dataclass(frozen=True)
class PairExtractionSummary:
    total_raw_events: int
    bilateral_events_extracted: int
    skipped_null_actor_events: int
    unique_pairs_count: int


async def extract_trailing_365d_bilateral_events(
    conn: AsyncConnection,
    target_date: date,
    lookback_days: int = 365,
) -> tuple[dict[tuple[str, str], list[EventScoringInput]], dict[tuple[str, str], date], PairExtractionSummary]:
    """Fetch trailing 365 days of gdelt_events, extract bilateral pairs, and log null actor skips.

    Returns:
        - events_by_pair: Dict mapping canonical (country_a, country_b) -> List[EventScoringInput]
        - last_event_dates: Dict mapping canonical (country_a, country_b) -> all-time MAX(event_date)
        - summary: PairExtractionSummary
    """
    start_date = target_date - date.resolution * lookback_days

    async with conn.cursor() as cur:
        # 1. Fetch trailing 365 days events where both actor country codes exist
        await cur.execute(
            """
            SELECT global_event_id, event_date,
                   actor1_country_code, actor2_country_code,
                   quad_class, goldstein_scale, avg_tone,
                   num_mentions, num_sources, num_articles
            FROM gdelt_events
            WHERE event_date >= %s AND event_date <= %s
              AND actor1_country_code IS NOT NULL AND actor1_country_code != ''
              AND actor2_country_code IS NOT NULL AND actor2_country_code != ''
              AND actor1_country_code != actor2_country_code
            ORDER BY event_date ASC
            """,
            (start_date, target_date),
        )
        rows = await cur.fetchall()

        # 2. Count null/invalid actor skips in trailing 365-day window
        await cur.execute(
            """
            SELECT COUNT(*)
            FROM gdelt_events
            WHERE event_date >= %s AND event_date <= %s
              AND (
                  actor1_country_code IS NULL OR actor1_country_code = ''
                  OR actor2_country_code IS NULL OR actor2_country_code = ''
                  OR actor1_country_code = actor2_country_code
              )
            """,
            (start_date, target_date),
        )
        skipped_null_count = (await cur.fetchone())[0]

        # 3. Fetch all-time MAX(event_date) for all bilateral pairs across the entire database
        await cur.execute(
            """
            SELECT LEAST(actor1_country_code, actor2_country_code) AS country_a,
                   GREATEST(actor1_country_code, actor2_country_code) AS country_b,
                   MAX(event_date) AS last_date
            FROM gdelt_events
            WHERE actor1_country_code IS NOT NULL AND actor1_country_code != ''
              AND actor2_country_code IS NOT NULL AND actor2_country_code != ''
              AND actor1_country_code != actor2_country_code
            GROUP BY LEAST(actor1_country_code, actor2_country_code),
                     GREATEST(actor1_country_code, actor2_country_code)
            """
        )
        all_time_last_dates_raw = await cur.fetchall()

    target_set = set(TARGET_COUNTRIES)
    events_by_pair: dict[tuple[str, str], list[EventScoringInput]] = {}
    extracted_count = 0

    for r in rows:
        c1, c2 = r[2].strip(), r[3].strip()
        if c1 in target_set and c2 in target_set:
            c_a = min(c1, c2)
            c_b = max(c1, c2)
            pair = (c_a, c_b)

            ev = EventScoringInput(
                global_event_id=r[0],
                quad_class=r[4],
                goldstein_scale=float(r[5]) if r[5] is not None else None,
                avg_tone=float(r[6]) if r[6] is not None else None,
                num_mentions=r[7],
                num_sources=r[8],
                num_articles=r[9],
            )
            events_by_pair.setdefault(pair, []).append(ev)
            extracted_count += 1

    last_event_dates: dict[tuple[str, str], date] = {}
    for r in all_time_last_dates_raw:
        c1, c2 = r[0].strip(), r[1].strip()
        if c1 in target_set and c2 in target_set:
            pair = (min(c1, c2), max(c1, c2))
            last_event_dates[pair] = r[2]

    summary = PairExtractionSummary(
        total_raw_events=len(rows) + skipped_null_count,
        bilateral_events_extracted=extracted_count,
        skipped_null_actor_events=skipped_null_count,
        unique_pairs_count=len(events_by_pair),
    )

    logger.info(
        "bilateral_pairs_extracted",
        extra={
            "target_date": str(target_date),
            "total_raw": summary.total_raw_events,
            "extracted": summary.bilateral_events_extracted,
            "skipped_null": summary.skipped_null_actor_events,
            "unique_pairs": summary.unique_pairs_count,
        },
    )

    return events_by_pair, last_event_dates, summary
