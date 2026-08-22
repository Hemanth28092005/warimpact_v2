"""BFS Cascade & Contagion Detector for Phase 4 Cross-Stream Correlation.

Algorithm:
  For each source country A with spike dates S_A:
    For each graph-adjacent neighbor B:
      co_spike_count = count of dates D in S_A where B spiked on any date in [D, D + window_days]
      contagion_score = co_spike_count / len(S_A)

Freshness Gating & State Tracking:
- Gated on CII freshness: Verifies MAX(score_date) in country_instability_index >= target_date - 7 days.
- If upstream CII is stale or empty, refuses to overwrite current cascade scores and records 'stale_input' / 'insufficient_data'.
- Tracks all executions in the `cascade_runs` table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from psycopg import AsyncConnection

from models.cascade.adjacency import build_country_adjacency_graph, CountryAdjacencyGraph
from models.cascade.spike import detect_country_spikes, load_active_model_version, DEFAULT_K

DEFAULT_WINDOW_DAYS: int = 7
CII_STALENESS_THRESHOLD_DAYS: int = 7


@dataclass
class CascadePairResult:
    source_country: str
    target_country: str
    contagion_score: float
    co_spike_count: int
    source_spike_count: int
    window_days: int
    analysis_start_date: date
    analysis_end_date: date


@dataclass
class CascadeRunExecution:
    run_id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    calculation_status: str  # 'computed', 'no_spikes', 'insufficient_data', 'stale_input', 'failed'
    failure_reason: str | None
    cii_max_score_date: date | None
    source_data_freshness_hours: float | None
    model_version: str
    window_days: int
    pairs_calculated: int
    pairs_published: int
    results: list[CascadePairResult]


async def check_cii_freshness(
    conn: AsyncConnection,
    model_version: str | None = None,
    target_date: date | None = None,
) -> tuple[bool, date | None, float | None, str | None]:
    """Check whether upstream CII predictions in country_instability_index are fresh and sufficient.

    Returns:
        (is_fresh: bool, max_score_date: date | None, freshness_hours: float | None, reason: str | None)
    """
    if model_version is None:
        model_version = load_active_model_version()
    if target_date is None:
        target_date = date.today()

    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT MAX(score_date), COUNT(*)
            FROM country_instability_index
            WHERE model_version = %s;
            """,
            (model_version,),
        )
        row = await cur.fetchone()
        max_date = row[0] if row else None
        total_rows = row[1] if row else 0

        # Fallback to check across any model_version if specific one is empty
        if not max_date:
            await cur.execute("SELECT MAX(score_date), COUNT(*) FROM country_instability_index;")
            row_fallback = await cur.fetchone()
            max_date = row_fallback[0] if row_fallback else None
            total_rows = row_fallback[1] if row_fallback else 0

    if not max_date or total_rows < 100:
        return False, max_date, None, f"Insufficient CII data in country_instability_index (found {total_rows} rows)"

    days_lag = (target_date - max_date).days
    freshness_hours = round(days_lag * 24.0, 1)

    if days_lag > CII_STALENESS_THRESHOLD_DAYS:
        return (
            False,
            max_date,
            freshness_hours,
            f"Upstream CII data is stale: MAX(score_date)={max_date} lags target date {target_date} by {days_lag} days (> {CII_STALENESS_THRESHOLD_DAYS}d threshold)",
        )

    return True, max_date, freshness_hours, None


async def compute_cascade_contagion(
    conn: AsyncConnection,
    window_days: int = DEFAULT_WINDOW_DAYS,
    k: float = DEFAULT_K,
    top_n_event_links: int = 5,
    model_version: str | None = None,
    target_date: date | None = None,
) -> CascadeRunExecution:
    """Execute BFS cascade analysis across graph neighbors with strict freshness gating.

    Returns CascadeRunExecution with calculation status, metadata, and results.
    """
    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    if model_version is None:
        model_version = load_active_model_version()
    if target_date is None:
        target_date = date.today()

    # Step 1: Enforce CII Freshness Gate
    is_fresh, max_cii_date, freshness_hours, failure_reason = await check_cii_freshness(
        conn, model_version=model_version, target_date=target_date
    )

    if not is_fresh:
        calc_status = "insufficient_data" if max_cii_date is None else "stale_input"
        return CascadeRunExecution(
            run_id=run_id,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            calculation_status=calc_status,
            failure_reason=failure_reason,
            cii_max_score_date=max_cii_date,
            source_data_freshness_hours=freshness_hours,
            model_version=model_version,
            window_days=window_days,
            pairs_calculated=0,
            pairs_published=0,
            results=[],
        )

    # Step 2: Build adjacency graph
    graph = await build_country_adjacency_graph(conn, top_n_event_links=top_n_event_links)

    # Step 3: Detect spike dates for all countries
    country_spikes = await detect_country_spikes(conn, k=k, model_version=model_version)

    # Step 4: Determine analysis date range
    async with conn.cursor() as cur:
        await cur.execute("SELECT MIN(score_date), MAX(score_date) FROM country_instability_index")
        r = await cur.fetchone()
        start_date = r[0] if r and r[0] else date(2025, 7, 28)
        end_date = r[1] if r and r[1] else date(2026, 7, 31)

    results: list[CascadePairResult] = []
    total_spikes = sum(len(spikes) for spikes in country_spikes.values())

    if total_spikes == 0:
        return CascadeRunExecution(
            run_id=run_id,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            calculation_status="no_spikes",
            failure_reason=f"No CII spikes exceeded threshold K={k} during analysis window",
            cii_max_score_date=max_cii_date,
            source_data_freshness_hours=freshness_hours,
            model_version=model_version,
            window_days=window_days,
            pairs_calculated=0,
            pairs_published=0,
            results=[],
        )

    # Step 5: For each source country, evaluate graph neighbors
    for source in graph.nodes:
        source_spikes = country_spikes.get(source, set())
        source_count = len(source_spikes)

        neighbors = graph.neighbors(source)
        for target in neighbors:
            target_spikes = country_spikes.get(target, set())

            co_spike_count = 0
            if source_count > 0:
                for spike_d in source_spikes:
                    has_co_spike = any(
                        (spike_d + timedelta(days=d_offset)) in target_spikes
                        for d_offset in range(window_days + 1)
                    )
                    if has_co_spike:
                        co_spike_count += 1

            contagion_score = round(co_spike_count / source_count, 4) if source_count > 0 else 0.0

            results.append(
                CascadePairResult(
                    source_country=source,
                    target_country=target,
                    contagion_score=contagion_score,
                    co_spike_count=co_spike_count,
                    source_spike_count=source_count,
                    window_days=window_days,
                    analysis_start_date=start_date,
                    analysis_end_date=end_date,
                )
            )

    return CascadeRunExecution(
        run_id=run_id,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        calculation_status="computed",
        failure_reason=None,
        cii_max_score_date=max_cii_date,
        source_data_freshness_hours=freshness_hours,
        model_version=model_version,
        window_days=window_days,
        pairs_calculated=len(results),
        pairs_published=len(results),
        results=results,
    )
