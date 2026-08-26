"""FastAPI router for seismic events near monitored chokepoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ingestion.common.db import open_async_connection

router = APIRouter(prefix="/api/v1/events", tags=["Events"])


@router.get("/earthquakes")
async def get_earthquakes(
    hours: int = Query(default=168, ge=1, le=720),
    min_magnitude: float = Query(default=2.5, ge=0.0, le=12.0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT external_id, magnitude, place, latitude, longitude, depth_km,
                       tsunami_flag, near_chokepoint_code, distance_to_chokepoint_km,
                       occurred_at
                FROM seismic_events
                WHERE occurred_at >= NOW() - (%s || ' hours')::interval
                  AND magnitude >= %s
                ORDER BY occurred_at DESC
                LIMIT %s
                """,
                (hours, min_magnitude, limit),
            )
            rows = await cur.fetchall()
    return [
        {
            "external_id": r[0],
            "magnitude": float(r[1]),
            "place": r[2],
            "latitude": float(r[3]),
            "longitude": float(r[4]),
            "depth_km": float(r[5]) if r[5] is not None else None,
            "tsunami_flag": bool(r[6]),
            "near_chokepoint_code": r[7],
            "distance_to_chokepoint_km": float(r[8]) if r[8] is not None else None,
            "occurred_at": r[9].isoformat(),
        }
        for r in rows
    ]


@router.get("/prediction-markets")
async def get_prediction_markets(limit: int = Query(default=25, ge=1, le=100)) -> list[dict[str, Any]]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT market_slug, question, platform, category, yes_price,
                       volume_24h_usd, end_date, url, fetched_at
                FROM prediction_markets
                ORDER BY volume_24h_usd DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
    return [
        {
            "market_slug": r[0],
            "question": r[1],
            "platform": r[2],
            "category": r[3],
            "yes_price": float(r[4]) if r[4] is not None else None,
            "volume_24h_usd": float(r[5]) if r[5] is not None else None,
            "end_date": r[6].isoformat() if r[6] is not None else None,
            "url": r[7],
            "fetched_at": r[8].isoformat(),
        }
        for r in rows
    ]


@router.get("/flights")
async def get_military_flights(limit: int = Query(default=500, ge=1, le=2000)) -> list[dict[str, Any]]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT hex_code, registration, aircraft_type, callsign, latitude, longitude,
                       altitude_ft, ground_speed_kt, squawk, observed_at
                FROM military_flights
                WHERE observed_at >= NOW() - interval '30 minutes'
                ORDER BY observed_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
    return [
        {
            "hex": r[0],
            "registration": r[1],
            "aircraft_type": r[2],
            "callsign": r[3],
            "latitude": float(r[4]),
            "longitude": float(r[5]),
            "altitude_ft": r[6],
            "ground_speed_kt": float(r[7]) if r[7] is not None else None,
            "squawk": r[8],
            "observed_at": r[9].isoformat(),
        }
        for r in rows
    ]


@router.get("/intel")
async def get_intel_layers() -> dict[str, list[dict[str, Any]]]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT category, name, country_code, latitude, longitude, is_estimated FROM intel_sites ORDER BY category, name"
            )
            site_rows = await cur.fetchall()
            await cur.execute(
                "SELECT category, name, from_name, from_lat, from_long, to_name, to_lat, to_long, is_estimated FROM intel_routes ORDER BY category, name"
            )
            route_rows = await cur.fetchall()
    return {
        "sites": [
            {
                "category": r[0],
                "name": r[1],
                "country_code": r[2],
                "latitude": float(r[3]),
                "longitude": float(r[4]),
                "is_estimated": bool(r[5]),
            }
            for r in site_rows
        ],
        "routes": [
            {
                "category": r[0],
                "name": r[1],
                "from_name": r[2],
                "from_lat": float(r[3]),
                "from_long": float(r[4]),
                "to_name": r[5],
                "to_lat": float(r[6]),
                "to_long": float(r[7]),
                "is_estimated": bool(r[8]),
            }
            for r in route_rows
        ],
    }
