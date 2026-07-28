"""Conflict intensity aggregation and sentiment signal computation per country-day."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from psycopg import AsyncConnection

from ingestion.common.logger import get_logger
from models.sentiment.scorer import EventSentimentResult

logger = get_logger(__name__)


@dataclass(frozen=True)
class CountryDailySignal:
    country_code: str
    signal_date: date
    event_count: int
    conflict_event_count: int
    material_conflict_count: int
    avg_goldstein: float | None
    weighted_conflict_intensity: float
    normalized_conflict_intensity: float  # Bounded in [0.0, 1.0]
    sentiment_score: float  # Bounded in [-1.0, 1.0]
    sentiment_sample_size: int
    sentiment_confidence: float
    computed_at: datetime


async def compute_and_save_country_signals(
    conn: AsyncConnection,
    target_date: date,
    sentiment_results: Sequence[EventSentimentResult],
) -> list[CountryDailySignal]:
    """Compute per-country daily conflict intensity and sentiment signals and upsert into DB."""
    # 1. Fetch raw country-day event metrics for target_date from gdelt_events
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT
                COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code) AS country_code,
                COUNT(*) AS event_count,
                COUNT(*) FILTER (WHERE quad_class IN (3, 4)) AS conflict_event_count,
                COUNT(*) FILTER (WHERE quad_class = 4) AS material_conflict_count,
                AVG(goldstein_scale) AS avg_goldstein,
                COALESCE(
                    SUM(
                        CASE WHEN quad_class IN (3, 4)
                             THEN COALESCE(num_mentions, 1) * ABS(COALESCE(goldstein_scale, 1.0))
                             ELSE 0 END
                    ), 0.0
                ) AS raw_weighted_intensity
            FROM gdelt_events
            WHERE event_date = %s
              AND COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code) IS NOT NULL
            GROUP BY COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code)
            """,
            (target_date,),
        )
        rows = await cur.fetchall()

    if not rows:
        logger.info("no_country_events_found_for_date", extra={"target_date": str(target_date)})
        return []

    # Map sentiment results by global_event_id and lookup country for sentiment grouping
    # Build lookup of event -> country & sentiment
    event_country_map: dict[int, str] = {}
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT global_event_id,
                   COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code) AS country_code
            FROM gdelt_events
            WHERE event_date = %s
            """,
            (target_date,),
        )
        for r in await cur.fetchall():
            if r[1]:
                event_country_map[r[0]] = r[1]

    sentiment_by_country: dict[str, list[EventSentimentResult]] = {}
    for res in sentiment_results:
        country = event_country_map.get(res.global_event_id)
        if country:
            sentiment_by_country.setdefault(country, []).append(res)

    computed_at = datetime.now(timezone.utc)
    signals: list[CountryDailySignal] = []

    for r in rows:
        country = r[0]
        if not country:
            continue
        event_count = int(r[1])
        conflict_count = int(r[2])
        material_count = int(r[3])
        avg_goldstein = float(r[4]) if r[4] is not None else None
        weighted_intensity = float(r[5])

        # 2. Compute 90-day rolling min-max normalization
        normalized_intensity = await _compute_normalized_intensity(
            conn, country, target_date, weighted_intensity
        )

        # 3. Compute country sentiment summary
        c_sentiments = sentiment_by_country.get(country, [])
        if c_sentiments:
            avg_sentiment = sum(s.sentiment_score for s in c_sentiments) / len(c_sentiments)
            avg_confidence = sum(s.confidence for s in c_sentiments) / len(c_sentiments)
            sample_size = len(c_sentiments)
        else:
            avg_sentiment = 0.0
            avg_confidence = 0.0
            sample_size = 0

        # Bound values to schema requirements
        bounded_normalized = max(0.0, min(1.0, round(normalized_intensity, 4)))
        bounded_sentiment = max(-1.0, min(1.0, round(avg_sentiment, 4)))
        bounded_confidence = max(0.0, min(1.0, round(avg_confidence, 3)))

        signals.append(
            CountryDailySignal(
                country_code=country,
                signal_date=target_date,
                event_count=event_count,
                conflict_event_count=conflict_count,
                material_conflict_count=material_count,
                avg_goldstein=avg_goldstein,
                weighted_conflict_intensity=round(weighted_intensity, 4),
                normalized_conflict_intensity=bounded_normalized,
                sentiment_score=bounded_sentiment,
                sentiment_sample_size=sample_size,
                sentiment_confidence=bounded_confidence,
                computed_at=computed_at,
            )
        )

    # 4. Count skipped null country events for run logging
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT COUNT(*)
            FROM gdelt_events
            WHERE event_date = %s
              AND (COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code) IS NULL
                   OR COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code) = '')
            """,
            (target_date,),
        )
        null_country_events_count = (await cur.fetchone())[0]

    # 5. Upsert into country_daily_signals table
    await _upsert_country_signals(conn, signals)

    logger.info(
        "country_daily_signals_computed",
        extra={
            "target_date": str(target_date),
            "countries_count": len(signals),
            "skipped_null_country_events": null_country_events_count,
        },
    )
    return signals


async def _compute_normalized_intensity(
    conn: AsyncConnection,
    country_code: str,
    target_date: date,
    current_weighted_intensity: float,
) -> float:
    """Compute rolling 90-day min-max scaling of weighted_conflict_intensity in [0.0, 1.0]."""
    start_date = target_date - timedelta(days=90)
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT weighted_conflict_intensity
            FROM country_daily_signals
            WHERE country_code = %s AND signal_date BETWEEN %s AND %s
            """,
            (country_code, start_date, target_date),
        )
        historical_values = [float(r[0]) for r in await cur.fetchall()]

    all_values = historical_values + [current_weighted_intensity]
    min_val = min(all_values)
    max_val = max(all_values)

    if max_val > min_val:
        return (current_weighted_intensity - min_val) / (max_val - min_val)
    return 0.0


async def _upsert_country_signals(
    conn: AsyncConnection,
    signals: Sequence[CountryDailySignal],
) -> None:
    """Upsert country daily signal records into country_daily_signals table."""
    if not signals:
        return

    sql = """
    INSERT INTO country_daily_signals (
        country_code, signal_date, event_count, conflict_event_count, material_conflict_count,
        avg_goldstein, weighted_conflict_intensity, normalized_conflict_intensity,
        sentiment_score, sentiment_sample_size, sentiment_confidence, computed_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (country_code, signal_date) DO UPDATE SET
        event_count = EXCLUDED.event_count,
        conflict_event_count = EXCLUDED.conflict_event_count,
        material_conflict_count = EXCLUDED.material_conflict_count,
        avg_goldstein = EXCLUDED.avg_goldstein,
        weighted_conflict_intensity = EXCLUDED.weighted_conflict_intensity,
        normalized_conflict_intensity = EXCLUDED.normalized_conflict_intensity,
        sentiment_score = EXCLUDED.sentiment_score,
        sentiment_sample_size = EXCLUDED.sentiment_sample_size,
        sentiment_confidence = EXCLUDED.sentiment_confidence,
        computed_at = EXCLUDED.computed_at
    """
    params = [
        (
            s.country_code,
            s.signal_date,
            s.event_count,
            s.conflict_event_count,
            s.material_conflict_count,
            Decimal(str(round(s.avg_goldstein, 3))) if s.avg_goldstein is not None else None,
            Decimal(str(s.weighted_conflict_intensity)),
            Decimal(str(s.normalized_conflict_intensity)),
            Decimal(str(s.sentiment_score)),
            s.sentiment_sample_size,
            Decimal(str(s.sentiment_confidence)),
            s.computed_at,
        )
        for s in signals
    ]

    async with conn.cursor() as cur:
        await cur.executemany(sql, params)
    await conn.commit()
