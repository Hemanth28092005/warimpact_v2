"""BFS Cascade & Contagion Detector for Phase 4 Cross-Stream Correlation.

Algorithm:
  For each source country A with spike dates S_A:
    For each graph-adjacent neighbor B:
      co_spike_count = count of dates D in S_A where B spiked on any date in [D, D + window_days]
      contagion_score = co_spike_count / len(S_A)

Non-Negotiable System Limitations & Analytical Disclaimers:
1. Correlation != Causation:
   Shared external macro shocks (e.g., a global or regional crisis affecting multiple countries
   simultaneously) can produce co-occurring CII spikes without direct contagion between the countries.

2. Statistical Association Measure:
   contagion_score measures empirical temporal co-occurrence of statistical outliers within an N-day window.
   It is NOT a structural or causal dynamic model.

3. Signal Confounding & Spurious Correlations:
   CII is derived from GDELT conflict and sentiment signals. Without cross-referencing secondary streams
   (e.g., Phase 5 trade exposure, bilateral capital flows), spurious correlations cannot be ruled out.

4. Fixed-Sigma Spike Threshold Bias:
   Because spike detection uses an absolute K*std threshold, it is miscalibrated across countries with
   different baseline volatility. Stable countries with naturally low CII variance (e.g. ESP, std~3.65)
   register 'spikes' from routine noise (+3-10 point moves) far more often than chronically volatile countries
   (e.g. YEM, std much higher, operating near the 100.00 score ceiling), where even severe real escalations
   often fail to exceed a 2-sigma threshold. Empirically: ESP registered 46 spike days vs. YEM's 11, despite
   YEM undergoing well-documented severe escalation during this period. Consequently, cascade contagion scores
   for conflict-cluster country pairs (e.g. SYR-YEM, SDN-SSD, ISR-SYR: 0.00-0.25) are systematically LOWER
   than for stable-country pairs (e.g. DEU-ITA, USA-CAN: 0.48-0.73) — this should NOT be read as evidence
   that contagion is weaker among conflict-prone countries; it is a detector calibration artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from psycopg import AsyncConnection

from models.cascade.adjacency import build_country_adjacency_graph, CountryAdjacencyGraph
from models.cascade.spike import detect_country_spikes, DEFAULT_K

DEFAULT_WINDOW_DAYS: int = 7


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


async def compute_cascade_contagion(
    conn: AsyncConnection,
    window_days: int = DEFAULT_WINDOW_DAYS,
    k: float = DEFAULT_K,
    top_n_event_links: int = 5,
) -> list[CascadePairResult]:
    """Execute BFS cascade analysis across graph neighbors and compute contagion scores.

    Args:
        conn: Async PostgreSQL connection.
        window_days: Trailing window in days to detect target co-spikes (default 7).
        k: Rolling stddev multiplier for spike threshold (default 2.0).
        top_n_event_links: Top bilateral event volume pairs for graph construction.

    Returns:
        List of CascadePairResult for all evaluated adjacency pairs.
    """
    # 1. Build adjacency graph (border + event-linkage)
    graph = await build_country_adjacency_graph(conn, top_n_event_links=top_n_event_links)

    # 2. Detect spike dates for all countries
    country_spikes = await detect_country_spikes(conn, k=k)

    # 3. Determine analysis date range
    async with conn.cursor() as cur:
        await cur.execute("SELECT MIN(score_date), MAX(score_date) FROM country_instability_index")
        r = await cur.fetchone()
        start_date = r[0] if r and r[0] else date(2025, 7, 28)
        end_date = r[1] if r and r[1] else date(2026, 7, 31)

    results: list[CascadePairResult] = []

    # 4. For each source country, evaluate graph neighbors
    for source in graph.nodes:
        source_spikes = country_spikes.get(source, set())
        source_count = len(source_spikes)

        neighbors = graph.neighbors(source)
        for target in neighbors:
            target_spikes = country_spikes.get(target, set())

            co_spike_count = 0
            if source_count > 0:
                for spike_d in source_spikes:
                    # Check if target spiked on any day in [spike_d, spike_d + window_days]
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

    return results
