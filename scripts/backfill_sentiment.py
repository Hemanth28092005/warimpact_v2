"""Resumable driver script for 12-month sentiment pipeline backfill."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
from typing import Set

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.sentiment.worker import run_sentiment_pipeline

logger = get_logger(__name__)


async def get_already_processed_dates(start_date: date, end_date: date) -> Set[date]:
    """Retrieve dates between start_date and end_date that already have rows in country_daily_signals."""
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT signal_date
                FROM country_daily_signals
                WHERE signal_date >= %s AND signal_date <= %s
                """,
                (start_date, end_date),
            )
            rows = await cur.fetchall()
            return {r[0] for r in rows}


async def run_backfill(start_date: date, end_date: date) -> None:
    logger.info("sentiment_backfill_started", extra={"start_date": str(start_date), "end_date": str(end_date)})

    existing_dates = await get_already_processed_dates(start_date, end_date)
    logger.info("sentiment_backfill_existing_check", extra={"existing_dates_count": len(existing_dates)})

    current_date = start_date
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    while current_date <= end_date:
        if current_date in existing_dates:
            skipped_count += 1
            current_date += timedelta(days=1)
            continue

        try:
            summary = await run_sentiment_pipeline(target_date=current_date, is_historical_backfill=True)
            processed_count += 1
            logger.info(
                "sentiment_backfill_date_completed",
                extra={
                    "date": str(current_date),
                    "countries_signaled": summary.countries_signaled_count,
                    "sampled_events": summary.total_sampled_events,
                    "unique_urls": summary.unique_urls_count,
                    "skipped_nulls": summary.skipped_null_country_events,
                },
            )
        except Exception as exc:
            failed_count += 1
            logger.error(
                "sentiment_backfill_date_failed",
                extra={"date": str(current_date), "error": str(exc)},
            )

        current_date += timedelta(days=1)

    logger.info(
        "sentiment_backfill_completed",
        extra={
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill sentiment pipeline across date range")
    parser.add_argument("--start", default="2025-07-28", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-07-27", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    asyncio.run(run_backfill(start_date, end_date))


if __name__ == "__main__":
    main()
