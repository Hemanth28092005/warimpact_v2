"""FastAPI REST endpoints for Country Bilateral Aggression Scores."""

from __future__ import annotations

from typing import Any, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ingestion.common.db import open_async_connection
from models.aggression.cow_parser import TARGET_COUNTRIES

router = APIRouter(prefix="/api/v1/aggression", tags=["Bilateral Aggression"])


class AggressionPairResponse(BaseModel):
    country_a: str = Field(..., description="Lexicographically smaller ISO-3 country code")
    country_b: str = Field(..., description="Lexicographically larger ISO-3 country code")
    aggression_score: Optional[float] = Field(None, description="Score bounded in [0.0, 100.0] (higher = more hostile)")
    event_count: int = Field(..., description="Bilateral event count in trailing 365 days")
    data_source: str = Field(..., description="'gdelt_derived' or 'external_baseline'")
    baseline_source: Optional[str] = Field(None, description="Correlates of War citation string if external_baseline")
    baseline_data_year: Optional[int] = Field(None, description="Dataset coverage year (e.g. 2010 or 2012)")
    last_event_date: Optional[str] = Field(None, description="All-time date of most recent bilateral event (YYYY-MM-DD)")
    computed_at: str = Field(..., description="Timestamp of score computation")


class AggressionMatrixResponse(BaseModel):
    total_pairs: int
    pairs: list[AggressionPairResponse]


@router.get("/matrix", response_model=AggressionMatrixResponse)
async def get_aggression_matrix(
    data_source: Optional[str] = Query(None, description="Filter by data_source ('gdelt_derived' or 'external_baseline')")
) -> AggressionMatrixResponse:
    """Retrieve full matrix of all bilateral country aggression scores."""
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            if data_source:
                await cur.execute(
                    """
                    SELECT country_a, country_b, aggression_score, event_count,
                           data_source, baseline_source, baseline_data_year,
                           last_event_date, computed_at
                    FROM country_aggression_scores
                    WHERE data_source = %s
                    ORDER BY country_a, country_b
                    """,
                    (data_source,),
                )
            else:
                await cur.execute(
                    """
                    SELECT country_a, country_b, aggression_score, event_count,
                           data_source, baseline_source, baseline_data_year,
                           last_event_date, computed_at
                    FROM country_aggression_scores
                    ORDER BY country_a, country_b
                    """
                )
            rows = await cur.fetchall()

    results: list[AggressionPairResponse] = []
    for r in rows:
        results.append(
            AggressionPairResponse(
                country_a=r[0],
                country_b=r[1],
                aggression_score=float(r[2]) if r[2] is not None else None,
                event_count=r[3],
                data_source=r[4],
                baseline_source=r[5],
                baseline_data_year=r[6],
                last_event_date=str(r[7]) if r[7] else None,
                computed_at=r[8].isoformat() if r[8] else "",
            )
        )

    return AggressionMatrixResponse(total_pairs=len(results), pairs=results)


@router.get("/{country_code}", response_model=list[AggressionPairResponse])
async def get_country_aggression_pairs(
    country_code: str = Path(..., description="3-letter ISO country code (e.g. USA, RUS, CHN)")
) -> list[AggressionPairResponse]:
    """Retrieve all bilateral aggression scores involving a specific country."""
    code_upper = country_code.upper()
    if code_upper not in TARGET_COUNTRIES:
        raise HTTPException(status_code=404, detail=f"Country '{code_upper}' is not in 38 target scope")

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT country_a, country_b, aggression_score, event_count,
                       data_source, baseline_source, baseline_data_year,
                       last_event_date, computed_at
                FROM country_aggression_scores
                WHERE country_a = %s OR country_b = %s
                ORDER BY country_a, country_b
                """,
                (code_upper, code_upper),
            )
            rows = await cur.fetchall()

    results: list[AggressionPairResponse] = []
    for r in rows:
        results.append(
            AggressionPairResponse(
                country_a=r[0],
                country_b=r[1],
                aggression_score=float(r[2]) if r[2] is not None else None,
                event_count=r[3],
                data_source=r[4],
                baseline_source=r[5],
                baseline_data_year=r[6],
                last_event_date=str(r[7]) if r[7] else None,
                computed_at=r[8].isoformat() if r[8] else "",
            )
        )

    return results


@router.get("/{country_a}/{country_b}", response_model=AggressionPairResponse)
async def get_single_pair_aggression(
    country_a: str = Path(..., description="First ISO country code"),
    country_b: str = Path(..., description="Second ISO country code"),
) -> AggressionPairResponse:
    """Retrieve bilateral aggression score for a specific pair of countries."""
    c1, c2 = country_a.upper(), country_b.upper()
    if c1 == c2:
        raise HTTPException(status_code=400, detail="Country pair must involve two distinct countries")

    canonical_a = min(c1, c2)
    canonical_b = max(c1, c2)

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT country_a, country_b, aggression_score, event_count,
                       data_source, baseline_source, baseline_data_year,
                       last_event_date, computed_at
                FROM country_aggression_scores
                WHERE country_a = %s AND country_b = %s
                """,
                (canonical_a, canonical_b),
            )
            r = await cur.fetchone()

    if not r:
        raise HTTPException(
            status_code=404,
            detail=f"No bilateral score record found for pair ({canonical_a}, {canonical_b})",
        )

    return AggressionPairResponse(
        country_a=r[0],
        country_b=r[1],
        aggression_score=float(r[2]) if r[2] is not None else None,
        event_count=r[3],
        data_source=r[4],
        baseline_source=r[5],
        baseline_data_year=r[6],
        last_event_date=str(r[7]) if r[7] else None,
        computed_at=r[8].isoformat() if r[8] else "",
    )
