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
async def get_military_flights(
    limit: int = Query(default=500, ge=1, le=2000),
    hours: int = Query(default=2, ge=1, le=24, description="Query retention window in hours"),
) -> list[dict[str, Any]]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT hex_code, registration, aircraft_type, callsign, latitude, longitude,
                       altitude_ft, ground_speed_kt, squawk, observed_at
                FROM military_flights
                WHERE observed_at >= NOW() - (%s || ' hours')::interval
                   OR observed_at >= (SELECT MAX(observed_at) FROM military_flights) - interval '30 minutes'
                ORDER BY observed_at DESC
                LIMIT %s
                """,
                (hours, limit),
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
            await cur.execute(
                """
                SELECT code, name, country_code, flag_country, fleet_type, flagship,
                       composition, operational_area, latitude, longitude, status,
                       threat_level, mission_brief, source_citation, last_reported_at
                FROM naval_fleets
                ORDER BY threat_level = 'critical' DESC, name ASC
                """
            )
            fleet_rows = await cur.fetchall()
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
        "fleets": [
            {
                "code": r[0],
                "name": r[1],
                "country_code": r[2],
                "flag_country": r[3],
                "fleet_type": r[4],
                "flagship": r[5],
                "composition": r[6],
                "operational_area": r[7],
                "latitude": float(r[8]),
                "longitude": float(r[9]),
                "status": r[10],
                "threat_level": r[11],
                "mission_brief": r[12],
                "source_citation": r[13],
                "last_reported_at": r[14].isoformat() if hasattr(r[14], "isoformat") else str(r[14]),
            }
            for r in fleet_rows
        ],
    }


@router.get("/naval")
async def get_naval_fleets(
    country_code: str | None = Query(default=None, description="Filter by country code (e.g. USA, IND, CHN, GBR, FRA, RUS, NATO, IRN)"),
    fleet_type: str | None = Query(default=None, description="Filter by fleet type"),
    status: str | None = Query(default=None, description="Filter by deployment status"),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    query = """
        SELECT code, name, country_code, flag_country, fleet_type, flagship,
               composition, operational_area, latitude, longitude, status,
               threat_level, mission_brief, source_citation, last_reported_at
        FROM naval_fleets
        WHERE 1=1
    """
    params: list[Any] = []
    if country_code:
        query += " AND country_code = %s"
        params.append(country_code.upper().strip())
    if fleet_type:
        query += " AND fleet_type = %s"
        params.append(fleet_type.lower().strip())
    if status:
        query += " AND status = %s"
        params.append(status.lower().strip())

    query += " ORDER BY threat_level = 'critical' DESC, threat_level = 'elevated' DESC, name ASC LIMIT %s"
    params.append(limit)

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()

    return [
        {
            "code": r[0],
            "name": r[1],
            "country_code": r[2],
            "flag_country": r[3],
            "fleet_type": r[4],
            "flagship": r[5],
            "composition": r[6],
            "operational_area": r[7],
            "latitude": float(r[8]),
            "longitude": float(r[9]),
            "status": r[10],
            "threat_level": r[11],
            "mission_brief": r[12],
            "source_citation": r[13],
            "last_reported_at": r[14].isoformat() if hasattr(r[14], "isoformat") else str(r[14]),
        }
        for r in rows
    ]
