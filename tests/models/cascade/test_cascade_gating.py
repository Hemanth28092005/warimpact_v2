"""Tests for Cascade Freshness Gating and Run State Model."""

import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
from psycopg import AsyncConnection

from models.cascade.detector import (
    check_cii_freshness,
    compute_cascade_contagion,
    CascadeRunExecution,
)
from models.cascade.worker import record_cascade_run, save_cascade_scores


@pytest.mark.asyncio
async def test_stale_cii_gating_rejects_overwrite(test_async_conn: AsyncConnection):
    """Verify that when CII data is stale, cascade detector aborts with status 'stale_input' and does not write to cascade_scores."""
    # Seed stale CII data (e.g. 60 days in the past)
    stale_date = date(2026, 1, 1)
    async with test_async_conn.cursor() as cur:
        await cur.execute("DELETE FROM country_instability_index;")
        await cur.execute("DELETE FROM cascade_scores;")
        await cur.execute("DELETE FROM cascade_runs;")

        # Insert stale row
        await cur.execute(
            """
            INSERT INTO country_instability_index (
                country_code, score_date, cii_score, model_version,
                feature_snapshot, confidence_interval_low, confidence_interval_high
            ) VALUES ('USA', %s, 45.0, 'test-model-v1', '{}', 40.0, 50.0);
            """,
            (stale_date,),
        )
    await test_async_conn.commit()

    # Attempt cascade computation for today
    execution = await compute_cascade_contagion(
        test_async_conn,
        model_version="test-model-v1",
        target_date=date(2026, 8, 22),
    )

    assert execution.calculation_status in {"stale_input", "insufficient_data"}
    assert execution.failure_reason is not None
    assert "stale" in execution.failure_reason.lower() or "insufficient" in execution.failure_reason.lower()
    assert execution.pairs_published == 0

    # Save should do nothing
    published = await save_cascade_scores(execution)
    assert published == 0

    # Verify cascade_scores remains empty
    async with test_async_conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM cascade_scores;")
        cnt = (await cur.fetchone())[0]
        assert cnt == 0, "cascade_scores should not be updated when input is stale!"


@pytest.mark.asyncio
async def test_cascade_runs_state_recording(test_async_conn: AsyncConnection):
    """Verify that every cascade run records its audit state in the cascade_runs table."""
    test_run_id = uuid.uuid4()
    execution = CascadeRunExecution(
        run_id=test_run_id,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        calculation_status="stale_input",
        failure_reason="Upstream CII data is stale by 30 days",
        cii_max_score_date=date(2026, 7, 1),
        source_data_freshness_hours=720.0,
        model_version="cii-v20260803",
        window_days=7,
        pairs_calculated=0,
        pairs_published=0,
        results=[],
    )

    await record_cascade_run(execution)

    async with test_async_conn.cursor() as cur:
        await cur.execute("SELECT calculation_status, failure_reason, model_version FROM cascade_runs WHERE run_id = %s;", (test_run_id,))
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == "stale_input"
        assert row[1] == "Upstream CII data is stale by 30 days"
        assert row[2] == "cii-v20260803"
