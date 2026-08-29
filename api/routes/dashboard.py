"""FastAPI router for Phase 6a Dashboard Data Layer endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from ingestion.common.db import open_async_connection

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


class ChokepointResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    code: str = Field(..., description="Unique chokepoint identifier code (e.g. HORMUZ, MALACCA)")
    name: str = Field(..., description="Common name of the maritime chokepoint")
    lat: float = Field(..., description="Geographic latitude coordinate")
    long: float = Field(..., description="Geographic longitude coordinate")
    baseline_mbd: float = Field(..., description="Baseline transit volume in million barrels per day (EIA 2023)")
    source_year: int = Field(..., description="Source dataset publication year")
    disruption_score: float = Field(..., ge=0.0, le=100.0, description="Computed dynamic disruption score [0.0, 100.0]")
    status: str = Field(..., description="Disruption status badge: 'green', 'yellow', or 'red'")
    related_event_ids: list[int] = Field(default_factory=list, description="Recent proximate GDELT event IDs driving disruption")
    last_disruption_reason: Optional[str] = Field(None, description="Human-readable reason or threat summary")
    updated_at: str = Field(..., description="ISO timestamp of last update")


class TradeRouteResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int = Field(..., description="Unique trade route identifier")
    commodity_code: str = Field(..., description="Tracked commodity code (e.g. PETROLEUM_CRUDE)")
    partner_country: str = Field(..., description="3-letter ISO partner country code")
    primary_chokepoint: Optional[str] = Field(None, description="Primary maritime chokepoint code, or null if direct transit")
    origin_lat: float = Field(..., description="Origin latitude coordinate")
    origin_long: float = Field(..., description="Origin longitude coordinate")
    dest_lat: float = Field(..., description="Destination latitude coordinate (India)")
    dest_long: float = Field(..., description="Destination longitude coordinate (India)")
    dest_port_name: str = Field(..., description="Resolved destination landing port name (e.g. Vadinar Port, Gujarat)")
    dest_port_code: str = Field(..., description="Resolved destination landing port code (e.g. IN-VAD)")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Composite route risk score [0.0, 100.0]")
    updated_at: str = Field(..., description="ISO timestamp of last calculation")


class ProtestResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int = Field(..., description="Unique protest record identifier")
    city: Optional[str] = Field(None, description="City or region name of protest/demonstration")
    location_name: Optional[str] = Field(None, description="Granular venue or place name")
    location_level: Optional[str] = Field(None, description="Location precision level ('venue', 'city', 'district', 'state', 'national')")
    state: Optional[str] = Field(None, description="State or province name")
    country_code: Optional[str] = Field(None, description="ISO3 country code (e.g. IND)")
    event_date: str = Field(..., description="Event date (YYYY-MM-DD)")
    headline: str = Field(..., description="Extracted news headline or event description")
    action_geo_lat: Optional[float] = Field(None, description="Latitude of event")
    action_geo_long: Optional[float] = Field(None, description="Longitude of event")
    gdelt_event_id: Optional[int] = Field(None, description="GDELT global event ID reference")
    source_url: Optional[str] = Field(None, description="Source article URL")
    event_severity: float = Field(..., description="Event severity score [0.0, 100.0]")
    llm_brief: Optional[str] = Field(None, description="LLM-generated 1-2 sentence neutral summary brief")
    validation_source: Optional[str] = Field(None, description="Validation source ('groq', 'gemini', 'rules', 'acled')")
    updated_at: str = Field(..., description="ISO timestamp of record update")


class RegionalHeadlineResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int = Field(..., description="Unique headline record identifier")
    region: str = Field(..., description="Geographic region key (e.g. united_states, india, middle_east)")
    rank: int = Field(..., ge=1, le=10, description="Top-10 ranking within the region")
    headline: str = Field(..., description="Extracted article headline")
    gdelt_event_id: Optional[int] = Field(None, description="GDELT global event ID reference")
    source_url: Optional[str] = Field(None, description="Source article URL")
    published_at: Optional[str] = Field(None, description="Publication timestamp")
    llm_brief: Optional[str] = Field(None, description="LLM-generated 1-2 sentence neutral summary brief")
    validation_source: Optional[str] = Field(None, description="Validation source ('groq', 'gemini', 'rules')")
    updated_at: str = Field(..., description="ISO timestamp of record update")


class GovernmentActionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    rank: int = Field(..., ge=1, le=10, description="Top-10 ranking of government policy action")
    headline: str = Field(..., description="Extracted action headline")
    action_type: str = Field(..., description="Action category (e.g. diplomatic_policy)")
    gdelt_event_id: Optional[int] = Field(None, description="GDELT global event ID reference")
    source_url: Optional[str] = Field(None, description="Source article URL")
    published_at: Optional[str] = Field(None, description="Publication timestamp")
    llm_brief: Optional[str] = Field(None, description="LLM-generated 1-2 sentence neutral summary brief")
    validation_source: Optional[str] = Field(None, description="Validation source ('groq', 'gemini', 'rules')")
    updated_at: str = Field(..., description="ISO timestamp of record update")


class CommodityResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    commodity_code: str = Field(..., description="Unique commodity code identifier")
    name: str = Field(..., description="Human-readable commodity name")
    category: str = Field(..., description="Commodity sector / category (Energy, Precious Metals, Agriculture, etc.)")
    trade_type: str = Field(..., description="'import' or 'export'")
    annual_value_usd: float = Field(..., description="Annual trade value in USD")
    source_citation: str = Field(..., description="Official government / trade data source citation")
    created_at: str = Field(..., description="ISO timestamp of creation")


class CommodityNewsResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int = Field(..., description="Unique commodity news record identifier")
    commodity_code: str = Field(..., description="Tracked commodity code")
    rank: int = Field(..., description="Headline rank for the commodity")
    headline: str = Field(..., description="Extracted headline")
    gdelt_event_id: Optional[int] = Field(None, description="GDELT event ID")
    source_url: Optional[str] = Field(None, description="Source article URL")
    published_at: Optional[str] = Field(None, description="Publication date/timestamp")
    updated_at: str = Field(..., description="ISO timestamp of record update")


class WorldBoundaryResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    iso_a3: str = Field(..., description="3-letter ISO alpha-3 country code")
    name: str = Field(..., description="Country name")
    geojson: dict[str, Any] = Field(..., description="GeoJSON boundary feature")
    created_at: str = Field(..., description="ISO timestamp of creation")


# --- Endpoints ---

class AlertResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(..., description="Unique alert identifier")
    type: str = Field(..., description="Alert type: cii, chokepoint, flight, seismic, cascade")
    level: str = Field(..., description="Alert level: critical, warning, info")
    entity: str = Field(..., description="Entity identifier (country code, chokepoint code, etc.)")
    value: float = Field(..., description="Metric value that triggered the alert")
    message: str = Field(..., description="Human-readable alert message")
    timestamp: str = Field(..., description="ISO timestamp of alert generation")


@router.get("/alerts/recent", response_model=list[AlertResponse])
async def get_recent_alerts(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum alerts to return"),
) -> list[dict[str, Any]]:
    """Retrieve recent system alerts from cross-stream analysis."""
    import time
    from datetime import datetime, timedelta
    import uuid

    alerts = []

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            # CII critical/warning alerts
            await cur.execute(
                """
                SELECT country_code, cii_score
                FROM country_instability_index
                WHERE score_date = (SELECT MAX(score_date) FROM country_instability_index)
                  AND cii_score >= 50
                ORDER BY cii_score DESC
                """
            )
            for code, score in await cur.fetchall():
                level = "critical" if score >= 70 else "warning"
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "cii",
                    "level": level,
                    "entity": code,
                    "value": float(score),
                    "message": f"{code} CII {score:.1f} — {level.upper()}",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })

            # Chokepoint alerts
            await cur.execute(
                """
                SELECT code, name, disruption_score, status
                FROM chokepoints
                WHERE disruption_score >= 40
                ORDER BY disruption_score DESC
                """
            )
            for code, name, score, status in await cur.fetchall():
                level = "critical" if status == "critical" else "warning"
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "chokepoint",
                    "level": level,
                    "entity": code,
                    "value": float(score),
                    "message": f"{name} ({code}) disruption {score:.0f} — {status.upper()}",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })

            # Flight density near chokepoints
            await cur.execute(
                """
                SELECT cp.code, COUNT(*) as cnt
                FROM military_flights mf
                JOIN chokepoints cp ON ST_DWithin(
                    ST_MakePoint(mf.longitude, mf.latitude)::geography,
                    ST_MakePoint(cp.long, cp.lat)::geography,
                    100000
                )
                WHERE mf.observed_at >= NOW() - INTERVAL '2 hours'
                   OR mf.observed_at >= (SELECT MAX(observed_at) FROM military_flights) - interval '30 minutes'
                GROUP BY cp.code
                HAVING COUNT(*) >= 5
                """
            )
            for code, cnt in await cur.fetchall():
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "flight",
                    "level": "warning",
                    "entity": code,
                    "value": float(cnt),
                    "message": f"{cnt} military flights near {code} (last 30m)",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })

            # Seismic near chokepoints
            await cur.execute(
                """
                SELECT near_chokepoint_code, magnitude, place
                FROM seismic_events
                WHERE near_chokepoint_code IS NOT NULL
                  AND occurred_at >= NOW() - INTERVAL '24 hours'
                  AND magnitude >= 5.0
                ORDER BY magnitude DESC
                LIMIT 5
                """
            )
            for code, mag, place in await cur.fetchall():
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "seismic",
                    "level": "critical" if mag >= 6.0 else "warning",
                    "entity": code,
                    "value": float(mag),
                    "message": f"M{mag:.1f} quake near {code} ({place})",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })

            # Cascade contagion alerts
            await cur.execute(
                """
                SELECT source_country, target_country, contagion_score
                FROM cascade_scores
                WHERE window_days = 7
                  AND contagion_score >= 0.6
                ORDER BY contagion_score DESC
                LIMIT 5
                """
            )
            for src, tgt, score in await cur.fetchall():
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "cascade",
                    "level": "critical",
                    "entity": f"{src}->{tgt}",
                    "value": float(score),
                    "message": f"Cascade contagion {src}⇄{tgt}: {(score*100):.0f}% co-spike rate",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })

    # Sort by level (critical first) then by timestamp
    level_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (level_order.get(a["level"], 3), a["timestamp"]), reverse=True)

    return alerts[:limit]


@router.get("/chokepoints", response_model=list[ChokepointResponse])
async def get_chokepoints() -> list[dict[str, Any]]:
    """Retrieve all 13 global maritime chokepoints with dynamic disruption scores and status badges."""
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT code, name, lat, long, baseline_mbd, source_year,
                       disruption_score, status, related_event_ids,
                       last_disruption_reason, updated_at
                FROM chokepoints
                ORDER BY code;
                """
            )
            rows = await cur.fetchall()

    results = []
    for r in rows:
        events = r[8] if isinstance(r[8], list) else (json.loads(r[8]) if r[8] else [])
        results.append(
            {
                "code": r[0],
                "name": r[1],
                "lat": float(r[2]),
                "long": float(r[3]),
                "baseline_mbd": float(r[4]),
                "source_year": int(r[5]),
                "disruption_score": float(r[6]),
                "status": r[7],
                "related_event_ids": events,
                "last_disruption_reason": r[9],
                "updated_at": r[10].isoformat() if hasattr(r[10], "isoformat") else str(r[10]),
            }
        )
    return results


def _resolve_dest_port(dest_lat: float, dest_long: float) -> tuple[str, str]:
    if abs(dest_lat - 22.45) < 0.2 and abs(dest_long - 69.80) < 0.2:
        return "Vadinar / Sikka Port (Gujarat)", "IN-VAD"
    if abs(dest_lat - 21.1086) < 0.2 and abs(dest_long - 72.6358) < 0.2:
        return "Hazira / Surat Port (Gujarat)", "IN-HZR"
    if abs(dest_lat - 22.7441) < 0.2 and abs(dest_long - 69.7025) < 0.2:
        return "Mundra Commercial Port (Gujarat)", "IN-MUN"
    if abs(dest_lat - 22.8360) < 0.2 and abs(dest_long - 70.2185) < 0.2:
        return "Kandla (Deendayal) Port (Gujarat)", "IN-IXY"
    if abs(dest_lat - 21.7000) < 0.2 and abs(dest_long - 72.5800) < 0.2:
        return "Dahej Chemical & LNG Port (Gujarat)", "IN-DHJ"
    if abs(dest_lat - 18.9500) < 0.2 and abs(dest_long - 72.9500) < 0.2:
        return "Mumbai JNPT Port (Maharashtra)", "IN-BOM"
    if abs(dest_lat - 15.4167) < 0.2 and abs(dest_long - 73.8000) < 0.2:
        return "Mormugao Port (Goa)", "IN-MRM"
    if abs(dest_lat - 9.9656) < 0.2 and abs(dest_long - 76.2711) < 0.2:
        return "Cochin Port / Kochi LNG (Kerala)", "IN-COK"
    if abs(dest_lat - 8.7533) < 0.2 and abs(dest_long - 78.1633) < 0.2:
        return "Tuticorin Port [V.O.C] (Tamil Nadu)", "IN-TCR"
    if abs(dest_lat - 13.0844) < 0.2 and abs(dest_long - 80.2980) < 0.2:
        return "Chennai Port & Ennore (Tamil Nadu)", "IN-MAA"
    if abs(dest_lat - 16.9890) < 0.2 and abs(dest_long - 82.2874) < 0.2:
        return "Kakinada Deepwater Port (Andhra Pradesh)", "IN-KID"
    if abs(dest_lat - 17.6868) < 0.2 and abs(dest_long - 83.2986) < 0.2:
        return "Visakhapatnam Port (Andhra Pradesh)", "IN-VTZ"
    if abs(dest_lat - 20.2644) < 0.2 and abs(dest_long - 86.6085) < 0.2:
        return "Paradip Port (Odisha)", "IN-PRT"
    if abs(dest_lat - 22.0333) < 0.2 and abs(dest_long - 88.0833) < 0.2:
        return "Haldia / Kolkata Port (West Bengal)", "IN-HLD"
    return "Indian Maritime Port", "IN-GEN"


@router.get("/trade-routes", response_model=list[TradeRouteResponse])
async def get_trade_routes(
    commodity_code: Optional[str] = Query(None, description="Filter by specific commodity code"),
    partner_country: Optional[str] = Query(None, description="Filter by 3-letter ISO partner country code"),
) -> list[dict[str, Any]]:
    """Retrieve India bilateral trade routes and combined risk scores across tracked commodities."""
    query = """
        SELECT id, commodity_code, partner_country, primary_chokepoint,
               origin_lat, origin_long, dest_lat, dest_long, risk_score, updated_at
        FROM india_trade_routes
        WHERE 1=1
    """
    params: list[Any] = []
    if commodity_code:
        query += " AND commodity_code = %s"
        params.append(commodity_code.upper().strip())
    if partner_country:
        query += " AND partner_country = %s"
        params.append(partner_country.upper().strip())

    query += " ORDER BY id;"

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()

    results = []
    for r in rows:
        d_lat = float(r[6])
        d_long = float(r[7])
        p_name, p_code = _resolve_dest_port(d_lat, d_long)
        results.append(
            {
                "id": int(r[0]),
                "commodity_code": r[1],
                "partner_country": r[2],
                "primary_chokepoint": r[3],
                "origin_lat": float(r[4]),
                "origin_long": float(r[5]),
                "dest_lat": d_lat,
                "dest_long": d_long,
                "dest_port_name": p_name,
                "dest_port_code": p_code,
                "risk_score": float(r[8]),
                "updated_at": r[9].isoformat() if hasattr(r[9], "isoformat") else str(r[9]),
            }
        )
    return results


@router.get("/protests", response_model=list[ProtestResponse])
async def get_protests(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum protest events to return"),
    validation_source: Optional[str] = Query(None, description="Filter by validation source (e.g. 'acled', 'rules', 'groq')"),
    country_code: Optional[str] = Query(None, description="Filter by ISO3 country code (e.g. 'IND', 'PAK', 'BGD')"),
) -> list[dict[str, Any]]:
    """Retrieve recent civil unrest and protest demonstrations, prioritizing ACLED validated records."""
    query = """
        SELECT id, city, location_name, location_level, state, country_code,
               event_date, headline, action_geo_lat, action_geo_long,
               gdelt_event_id, source_url, event_severity, llm_brief,
               validation_source, updated_at
        FROM protests
        WHERE 1=1
    """
    params: list[Any] = []
    if validation_source:
        query += " AND validation_source = %s"
        params.append(validation_source.lower().strip())
    if country_code:
        query += " AND country_code = %s"
        params.append(country_code.upper().strip())

    query += """
        ORDER BY CASE WHEN validation_source = 'acled' THEN 0 ELSE 1 END, event_date DESC, id DESC
        LIMIT %s;
    """
    params.append(limit)

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()

    results = []
    for r in rows:
        results.append(
            {
                "id": int(r[0]),
                "city": r[1],
                "location_name": r[2],
                "location_level": r[3],
                "state": r[4],
                "country_code": r[5] or "IND",
                "event_date": str(r[6]),
                "headline": r[7],
                "action_geo_lat": float(r[8]) if r[8] is not None else None,
                "action_geo_long": float(r[9]) if r[9] is not None else None,
                "gdelt_event_id": int(r[10]) if r[10] is not None else None,
                "source_url": r[11],
                "event_severity": float(r[12]),
                "llm_brief": r[13],
                "validation_source": r[14],
                "updated_at": r[15].isoformat() if hasattr(r[15], "isoformat") else str(r[15]),
            }
        )
    return results


@router.get("/regional-headlines", response_model=list[RegionalHeadlineResponse])
async def get_regional_headlines(
    region: Optional[str] = Query(None, description="Filter by region (e.g. united_states, india, middle_east, europe, asia_pacific, africa, latin_america_australia)"),
) -> list[dict[str, Any]]:
    """Retrieve top-10 curated regional security and economic headlines across 7 global regions."""
    query = """
        SELECT id, region, rank, headline, gdelt_event_id, source_url, published_at, llm_brief, validation_source, updated_at
        FROM regional_headlines
        WHERE 1=1
    """
    params: list[Any] = []
    if region:
        query += " AND region = %s"
        params.append(region.lower().strip())

    query += " ORDER BY region, rank;"

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()

    results = []
    for r in rows:
        results.append(
            {
                "id": int(r[0]),
                "region": r[1],
                "rank": int(r[2]),
                "headline": r[3],
                "gdelt_event_id": int(r[4]) if r[4] is not None else None,
                "source_url": r[5],
                "published_at": r[6].isoformat() if hasattr(r[6], "isoformat") else (str(r[6]) if r[6] else None),
                "llm_brief": r[7],
                "validation_source": r[8],
                "updated_at": r[9].isoformat() if hasattr(r[9], "isoformat") else str(r[9]),
            }
        )
    return results


@router.get("/government-actions", response_model=list[GovernmentActionResponse])
async def get_government_actions() -> list[dict[str, Any]]:
    """Retrieve top-10 official government policy actions and diplomatic statements."""
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT rank, headline, action_type, gdelt_event_id, source_url, published_at, llm_brief, validation_source, updated_at
                FROM government_actions
                ORDER BY rank;
                """
            )
            rows = await cur.fetchall()

    results = []
    for r in rows:
        results.append(
            {
                "rank": int(r[0]),
                "headline": r[1],
                "action_type": r[2],
                "gdelt_event_id": int(r[3]) if r[3] is not None else None,
                "source_url": r[4],
                "published_at": r[5].isoformat() if hasattr(r[5], "isoformat") else (str(r[5]) if r[5] else None),
                "llm_brief": r[6],
                "validation_source": r[7],
                "updated_at": r[8].isoformat() if hasattr(r[8], "isoformat") else str(r[8]),
            }
        )
    return results


@router.get("/commodities", response_model=list[CommodityResponse])
async def get_tracked_commodities(
    category: Optional[str] = Query(None, description="Filter by category (e.g. Energy, Precious Metals, Agriculture)"),
    trade_type: Optional[str] = Query(None, description="Filter by trade type ('import' or 'export')"),
) -> list[dict[str, Any]]:
    """Retrieve all 30 tracked commodities (top 15 imports and top 15 exports by annual USD value)."""
    query = """
        SELECT commodity_code, name, category, trade_type, annual_value_usd, source_citation, created_at
        FROM tracked_commodities
        WHERE 1=1
    """
    params: list[Any] = []
    if category:
        query += " AND LOWER(category) = %s"
        params.append(category.lower().strip())
    if trade_type:
        query += " AND LOWER(trade_type) = %s"
        params.append(trade_type.lower().strip())

    query += " ORDER BY annual_value_usd DESC;"

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()

    results = []
    for r in rows:
        results.append(
            {
                "commodity_code": r[0],
                "name": r[1],
                "category": r[2],
                "trade_type": r[3],
                "annual_value_usd": float(r[4]),
                "source_citation": r[5],
                "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
            }
        )
    return results


@router.get("/commodity-news", response_model=list[CommodityNewsResponse])
async def get_commodity_news(
    commodity_code: Optional[str] = Query(None, description="Filter by specific commodity code"),
) -> list[dict[str, Any]]:
    """Retrieve matched commodity market and supply telemetry news items."""
    query = """
        SELECT id, commodity_code, rank, headline, gdelt_event_id, source_url, published_at, updated_at
        FROM commodity_news
        WHERE 1=1
    """
    params: list[Any] = []
    if commodity_code:
        query += " AND commodity_code = %s"
        params.append(commodity_code.upper().strip())

    query += " ORDER BY commodity_code, rank;"

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()

    results = []
    for r in rows:
        results.append(
            {
                "id": int(r[0]),
                "commodity_code": r[1],
                "rank": int(r[2]),
                "headline": r[3],
                "gdelt_event_id": int(r[4]) if r[4] is not None else None,
                "source_url": r[5],
                "published_at": r[6].isoformat() if hasattr(r[6], "isoformat") else (str(r[6]) if r[6] else None),
                "updated_at": r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7]),
            }
        )
    return results


@router.get("/boundaries", response_model=list[WorldBoundaryResponse])
async def get_world_boundaries(
    iso_a3: Optional[str] = Query(None, description="Filter by 3-letter ISO alpha-3 code"),
) -> list[dict[str, Any]]:
    """Retrieve full-globe GeoJSON country boundaries."""
    query = "SELECT iso_a3, name, geojson, created_at FROM world_boundaries WHERE 1=1"
    params: list[Any] = []
    if iso_a3:
        query += " AND iso_a3 = %s"
        params.append(iso_a3.upper().strip())

    query += " ORDER BY name;"

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()

    results = []
    for r in rows:
        geo = r[2] if isinstance(r[2], dict) else json.loads(r[2])
        results.append(
            {
                "iso_a3": r[0],
                "name": r[1],
                "geojson": geo,
                "created_at": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
            }
        )
    return results
