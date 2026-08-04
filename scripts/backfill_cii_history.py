"""Backfill country_instability_index using the active promoted CII model across full 366-day range."""

from __future__ import annotations

import sys
sys.path.insert(0, ".")

import asyncio
from datetime import date, timedelta
import time
from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.cii.inference import score_country_instability

logger = get_logger(__name__)


async def backfill_cii_scores(start_date: date, end_date: date) -> None:
    current_d = start_date
    dates = []
    while current_d <= end_date:
        dates.append(current_d)
        current_d += timedelta(days=1)

    total_dates = len(dates)
    logger.info("cii_backfill_started", extra={"start_date": str(start_date), "end_date": str(end_date), "total_dates": total_dates})

    start_time = time.time()
    total_scored = 0

    async with open_async_connection() as conn:
        for idx, target_d in enumerate(dates, 1):
            preds = await score_country_instability(conn, target_d)
            total_scored += len(preds)

            if idx % 30 == 0 or idx == total_dates:
                elapsed = time.time() - start_time
                print(f"[{idx}/{total_dates}] Backfilled {target_d} ({len(preds)} countries scored). Total: {total_scored} rows. Elapsed: {elapsed:.1f}s")

    elapsed = time.time() - start_time
    print(f"\nCII History Backfill Completed! Total dates: {total_dates}, Total predictions saved: {total_scored} in {elapsed:.1f}s.")


if __name__ == "__main__":
    start = date(2025, 7, 28)
    end = date(2026, 7, 31)
    asyncio.run(backfill_cii_scores(start, end))
