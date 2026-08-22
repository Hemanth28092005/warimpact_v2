"""CLI Worker for Phase 4 Cascade / Cross-Stream Correlation.

Usage:
  python -m models.cascade.worker
"""

from __future__ import annotations

import sys
import asyncio
from datetime import datetime, timezone
import time

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.cascade.detector import (
    compute_cascade_contagion,
    CascadeRunExecution,
    DEFAULT_WINDOW_DAYS,
)
from models.cascade.spike import DEFAULT_K, load_active_model_version

logger = get_logger(__name__)


async def record_cascade_run(execution: CascadeRunExecution) -> None:
    """Record cascade run state in cascade_runs table."""
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO cascade_runs (
                    run_id, started_at, completed_at, calculation_status, failure_reason,
                    cii_max_score_date, source_data_freshness_hours, model_version,
                    window_days, pairs_calculated, pairs_published
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    completed_at = EXCLUDED.completed_at,
                    calculation_status = EXCLUDED.calculation_status,
                    failure_reason = EXCLUDED.failure_reason,
                    pairs_published = EXCLUDED.pairs_published;
                """,
                (
                    execution.run_id,
                    execution.started_at,
                    execution.completed_at,
                    execution.calculation_status,
                    execution.failure_reason,
                    execution.cii_max_score_date,
                    execution.source_data_freshness_hours,
                    execution.model_version,
                    execution.window_days,
                    execution.pairs_calculated,
                    execution.pairs_published,
                ),
            )
        await conn.commit()


async def save_cascade_scores(execution: CascadeRunExecution) -> int:
    """Save or upsert cascade pair contagion results linked to run_id.

    Only executes if calculation_status is 'computed' or 'no_spikes'.
    """
    if execution.calculation_status not in {"computed", "no_spikes"}:
        logger.warning(
            f"Skipping cascade_scores publish: run status is '{execution.calculation_status}' ({execution.failure_reason})"
        )
        return 0

    if not execution.results:
        return 0

    computed_at = datetime.now(timezone.utc)

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            for r in execution.results:
                await cur.execute(
                    """
                    INSERT INTO cascade_scores (
                        source_country, target_country, contagion_score,
                        co_spike_count, source_spike_count, window_days,
                        analysis_start_date, analysis_end_date, computed_at, run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_country, target_country, window_days)
                    DO UPDATE SET
                        contagion_score = EXCLUDED.contagion_score,
                        co_spike_count = EXCLUDED.co_spike_count,
                        source_spike_count = EXCLUDED.source_spike_count,
                        analysis_start_date = EXCLUDED.analysis_start_date,
                        analysis_end_date = EXCLUDED.analysis_end_date,
                        computed_at = EXCLUDED.computed_at,
                        run_id = EXCLUDED.run_id;
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
                        execution.run_id,
                    ),
                )
        await conn.commit()

    return len(execution.results)


async def run_cascade_pipeline(
    window_days: int = DEFAULT_WINDOW_DAYS,
    k: float = DEFAULT_K,
) -> CascadeRunExecution:
    """Run full cascade contagion pipeline with state recording and score publishing."""
    start_time = time.monotonic()
    logger.info("cascade_pipeline_started", extra={"window_days": window_days, "k": k})

    async with open_async_connection() as conn:
        execution = await compute_cascade_contagion(conn, window_days=window_days, k=k)

    # 1. Record run state in cascade_runs
    await record_cascade_run(execution)

    # 2. Publish scores if valid
    if execution.calculation_status == "computed":
        published_count = await save_cascade_scores(execution)
        logger.info(
            "cascade_pipeline_completed",
            extra={
                "run_id": str(execution.run_id),
                "status": execution.calculation_status,
                "pairs_published": published_count,
                "duration_seconds": round(time.monotonic() - start_time, 2),
            },
        )
    else:
        logger.warning(
            "cascade_pipeline_aborted_stale_or_empty",
            extra={
                "run_id": str(execution.run_id),
                "status": execution.calculation_status,
                "reason": execution.failure_reason,
            },
        )

    return execution


def main() -> None:
    asyncio.run(run_cascade_pipeline())


if __name__ == "__main__":
    main()
