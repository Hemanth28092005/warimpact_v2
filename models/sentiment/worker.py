"""Worker orchestration for Phase 2 Sentiment and Conflict Signals pipeline."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.sentiment.article_fetcher import fetch_and_cache_articles, sample_events_for_fetching
from models.sentiment.scorer import score_events_sentiment
from models.sentiment.signals import compute_and_save_country_signals

logger = get_logger(__name__)


@dataclass(frozen=True)
class SentimentRunSummary:
    target_date: date
    total_sampled_events: int
    unique_urls_count: int
    countries_signaled_count: int
    skipped_null_country_events: int


async def run_sentiment_pipeline(
    target_date: date | None = None,
    is_historical_backfill: bool = False,
) -> SentimentRunSummary:
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    logger.info("sentiment_pipeline_started", extra={"target_date": str(target_date), "is_historical_backfill": is_historical_backfill})

    async with open_async_connection() as conn:
        # Step 1: Sample ~10% of events per country
        sampled_events = await sample_events_for_fetching(conn, target_date)
        unique_urls = list({e.source_url for e in sampled_events})

        if is_historical_backfill:
            # Step 2: Skip HTTP article fetching for historical backfill
            cached_articles = {}
            # Step 3: Score sentiment using composite historical formula
            sentiment_results = score_events_sentiment(sampled_events, cached_articles=None, is_historical_backfill=True)
        else:
            # Step 2: Check cache and fetch uncached article text
            cached_articles = await fetch_and_cache_articles(conn, unique_urls)
            # Step 3: Score sentiment (RoBERTa with AvgTone fallback)
            sentiment_results = score_events_sentiment(sampled_events, cached_articles=cached_articles, is_historical_backfill=False)

        # Step 4: Compute per-country signals & min-max conflict intensity
        signals = await compute_and_save_country_signals(conn, target_date, sentiment_results)

        # Step 5: Query null country events count
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
            null_count = (await cur.fetchone())[0]

    summary = SentimentRunSummary(
        target_date=target_date,
        total_sampled_events=len(sampled_events),
        unique_urls_count=len(unique_urls),
        countries_signaled_count=len(signals),
        skipped_null_country_events=null_count,
    )
    logger.info("sentiment_pipeline_completed", extra=summary.__dict__)
    return summary


def run_sentiment_pipeline_sync(
    target_date: date | None = None,
) -> dict[str, Any]:
    summary = asyncio.run(run_sentiment_pipeline(target_date=target_date))
    return {
        "target_date": str(summary.target_date),
        "total_sampled_events": summary.total_sampled_events,
        "unique_urls_count": summary.unique_urls_count,
        "countries_signaled_count": summary.countries_signaled_count,
        "skipped_null_country_events": summary.skipped_null_country_events,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 2 sentiment and signals pipeline")
    parser.add_argument("--date", help="Target signal date, ISO format (YYYY-MM-DD)")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    target_date = date.fromisoformat(args.date) if args.date else None
    print(run_sentiment_pipeline_sync(target_date=target_date))


if __name__ == "__main__":
    main()
