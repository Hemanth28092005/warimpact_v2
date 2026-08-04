"""Cascade / Cross-Stream Correlation API routes for Phase 4."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from ingestion.common.db import open_async_connection

cascade_router = APIRouter(prefix="/api/v1", tags=["Cascade"])


@cascade_router.get("/cascade/{country_code}")
async def get_country_cascade_scores(
    country_code: str,
    window_days: int = Query(default=7, ge=1, le=30, description="Cascade detection window in days"),
) -> dict[str, Any]:
    """Retrieve cascade contagion scores for all pairs involving the specified country.

    Args:
        country_code: ISO 3-letter country code (e.g. USA, YEM, UKR).
        window_days: Trailing cascade window in days (default 7).

    Returns:
        JSON response with list of cascade pair results.
    """
    code = country_code.upper().strip()
    if len(code) != 3:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid country_code '{country_code}'. Must be a 3-letter ISO alpha-3 code.",
        )

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT source_country, target_country, contagion_score,
                       co_spike_count, source_spike_count, window_days,
                       analysis_start_date, analysis_end_date, computed_at
                FROM cascade_scores
                WHERE (source_country = %s OR target_country = %s)
                  AND window_days = %s
                ORDER BY contagion_score DESC, co_spike_count DESC
                """,
                (code, code, window_days),
            )
            rows = await cur.fetchall()

    pairs = []
    for r in rows:
        pairs.append(
            {
                "source_country": r[0],
                "target_country": r[1],
                "contagion_score": float(r[2]),
                "co_spike_count": int(r[3]),
                "source_spike_count": int(r[4]),
                "window_days": int(r[5]),
                "analysis_start_date": r[6].isoformat() if r[6] else None,
                "analysis_end_date": r[7].isoformat() if r[7] else None,
                "computed_at": r[8].isoformat() if r[8] else None,
            }
        )

    return {
        "country_code": code,
        "window_days": window_days,
        "total_pairs": len(pairs),
        "pairs": pairs,
    }
