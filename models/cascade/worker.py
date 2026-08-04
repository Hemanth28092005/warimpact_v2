"""CLI Worker for Phase 4 Cascade / Cross-Stream Correlation.

Usage:
  python -m models.cascade.worker
"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")

import asyncio
from datetime import datetime, timezone
import time
from typing import Sequence

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.cascade.detector import compute_cascade_contagion, CascadePairResult, DEFAULT_WINDOW_DAYS
from models.cascade.spike import DEFAULT_K

logger = get_logger(__name__)


async def save_cascade_scores(
    results: Sequence[CascadePairResult],
) -> int:
    """Save or upsert cascade pair contagion results into cascade_scores table.

    Args:
        results: Sequence of CascadePairResult.

    Returns:
        Number of rows upserted.
    """
    if not results:
        return 0

    computed_at = datetime.now(timezone.utc)

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            for r in results:
                await cur.execute(
                    """
                    INSERT INTO cascade_scores (
                        source_country, target_country, contagion_score,
                        co_spike_count, source_spike_count, window_days,
                        analysis_start_date, analysis_end_date, computed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_country, target_country, window_days)
                    DO UPDATE SET
                        contagion_score = EXCLUDED.contagion_score,
                        co_spike_count = EXCLUDED.co_spike_count,
                        source_spike_count = EXCLUDED.source_spike_count,
                        analysis_start_date = EXCLUDED.analysis_start_date,
                        analysis_end_date = EXCLUDED.analysis_end_date,
                        computed_at = EXCLUDED.computed_at
                    """,
                    (
                        r.source_country,
                        r.target_country,
                        r.contagion_score,
                        r.co_spike_count,
                        r.source_spike_count,
                        r.window_days,
                        r.analysis_start_date,
                        r.analysis_end_date,
                        computed_at,
                    ),
                )
        await conn.commit()
    return len(results)


async def run_cascade_worker(
    window_days: int = DEFAULT_WINDOW_DAYS,
    k: float = DEFAULT_K,
) -> int:
    """Execute full cascade analysis worker and save results.

    Returns:
        Number of pairs processed.
    """
    start_ts = time.time()
    logger.info("cascade_worker_started", extra={"window_days": window_days, "k": k})

    async with open_async_connection() as conn:
        results = await compute_cascade_contagion(conn, window_days=window_days, k=k)

    saved_count = await save_cascade_scores(results)
    elapsed = time.time() - start_ts

    logger.info(
        "cascade_worker_completed",
        extra={"pairs_computed": len(results), "rows_saved": saved_count, "elapsed_seconds": round(elapsed, 2)},
    )
    print(f"Cascade Worker Completed! Processed {len(results)} pairs, saved {saved_count} rows in {elapsed:.2f}s.")
    return saved_count


if __name__ == "__main__":
    asyncio.run(run_cascade_worker())
