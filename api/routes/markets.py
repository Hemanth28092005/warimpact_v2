"""FastAPI router for market data: commodity prices, freight indices, prediction markets."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from psycopg import OperationalError as PsycopgOperationalError
from ingestion.common.db import open_async_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/markets", tags=["Markets"])


@router.get("/commodities")
async def get_commodity_prices(limit_per_code: int = Query(default=1, ge=1, le=24)) -> list[dict[str, Any]]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT ON (p.commodity_code)
                    p.commodity_code, t.name, t.category, p.price_usd, p.previous_close_usd,
                    p.change_pct, p.unit_label, p.data_source, p.observed_at
                FROM commodity_prices p
                JOIN tracked_commodities t ON t.commodity_code = p.commodity_code
                ORDER BY p.commodity_code, p.observed_at DESC
                """
            )
            rows = (await cur.fetchall()) if limit_per_code == 1 else None
            if rows is None:
                await cur.execute(
                    """
                    SELECT p.commodity_code, t.name, t.category, p.price_usd, p.previous_close_usd,
                           p.change_pct, p.unit_label, p.data_source, p.observed_at
                    FROM commodity_prices p
                    JOIN tracked_commodities t ON t.commodity_code = p.commodity_code
                    WHERE p.id IN (
                        SELECT id FROM (
                            SELECT id, ROW_NUMBER() OVER (PARTITION BY commodity_code ORDER BY observed_at DESC) rn
                            FROM commodity_prices
                        ) ranked WHERE rn <= %s
                    )
                    ORDER BY p.commodity_code, p.observed_at DESC
                    """,
                    (limit_per_code,),
                )
                rows = await cur.fetchall()
    return [
        {
            "commodity_code": r[0],
            "name": r[1],
            "category": r[2],
            "price_usd": float(r[3]),
            "previous_close_usd": float(r[4]) if r[4] is not None else None,
            "change_pct": float(r[5]) if r[5] is not None else None,
            "unit_label": r[6],
            "data_source": r[7],
            "observed_at": r[8].isoformat(),
        }
        for r in rows
    ]


@router.get("/shipping")
async def get_freight_indices(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT ON (index_code)
                    index_code, name, rate_usd, previous_rate_usd, change_pct,
                    unit_label, route_label, rate_date, data_source, is_estimated
                FROM freight_indices
                ORDER BY index_code, rate_date DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
    return [
        {
            "index_code": r[0],
            "name": r[1],
            "rate_usd": float(r[2]),
            "previous_rate_usd": float(r[3]) if r[3] is not None else None,
            "change_pct": float(r[4]) if r[4] is not None else None,
            "unit_label": r[5],
            "route_label": r[6],
            "rate_date": str(r[7]),
            "data_source": r[8],
            "is_estimated": bool(r[9]),
        }
        for r in rows
    ]
