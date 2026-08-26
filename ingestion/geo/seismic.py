"""USGS earthquake ingestion with chokepoint proximity attribution.

Pulls the USGS GeoJSON summary feeds and flags quakes within a configurable
radius of monitored maritime chokepoints so the dashboard can surface
potential infrastructure-disruption signals.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import radians, sin, cos, asin, sqrt
from typing import Any

import httpx
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

USGS_FEEDS = [
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson",
]

CHOKEPOINT_RADIUS_KM = 500.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lon1, lat1, lon2, lat2 = map(radians, (lon1, lat1, lon2, lat2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2.0 * asin(sqrt(a))


def fetch_quakes(timeout_seconds: float = 20.0) -> list[dict[str, Any]]:
    quakes: list[dict[str, Any]] = []
    seen: set[str] = set()
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        for feed in USGS_FEEDS:
            response = client.get(feed)
            response.raise_for_status()
            for feature in response.json().get("features", []):
                props = feature.get("properties", {}) or {}
                geom = feature.get("geometry", {}) or {}
                coords = (geom.get("coordinates") or [None, None, None])
                external_id = str(feature.get("id") or "")
                if not external_id or external_id in seen:
                    continue
                try:
                    mag = float(props["mag"])
                    lat = float(coords[1])
                    lon = float(coords[0])
                    occurred = int(props["time"]) / 1000.0
                except (TypeError, ValueError, KeyError, IndexError):
                    continue
                if mag < 2.5:
                    continue
                seen.add(external_id)
                quakes.append(
                    {
                        "external_id": external_id,
                        "magnitude": mag,
                        "place": props.get("place"),
                        "latitude": lat,
                        "longitude": lon,
                        "depth_km": float(coords[2]) if coords[2] is not None else None,
                        "tsunami_flag": bool(props.get("tsunami")),
                        "occurred_at": datetime.fromtimestamp(occurred, tz=timezone.utc),
                    }
                )
    return quakes


def load_chokepoints(conn: psycopg.Connection) -> list[tuple[str, float, float]]:
    with conn.cursor() as cur:
        cur.execute("SELECT code, lat::float, long::float FROM chokepoints")
        return [(str(r[0]), float(r[1]), float(r[2])) for r in cur.fetchall()]


def upsert_quakes(conn: psycopg.Connection, quakes: list[dict[str, Any]], chokepoints: list[tuple[str, float, float]]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for q in quakes:
            nearest_code = None
            nearest_km = None
            for code, clat, clon in chokepoints:
                km = haversine_km(q["latitude"], q["longitude"], clat, clon)
                if km <= CHOKEPOINT_RADIUS_KM and (nearest_km is None or km < nearest_km):
                    nearest_code = code
                    nearest_km = km
            cur.execute(
                """
                INSERT INTO seismic_events
                    (external_id, magnitude, place, latitude, longitude, depth_km,
                     tsunami_flag, near_chokepoint_code, distance_to_chokepoint_km, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_id) DO UPDATE SET
                    magnitude = EXCLUDED.magnitude,
                    place = EXCLUDED.place,
                    tsunami_flag = EXCLUDED.tsunami_flag
                """,
                (
                    q["external_id"],
                    q["magnitude"],
                    q["place"],
                    q["latitude"],
                    q["longitude"],
                    q["depth_km"],
                    q["tsunami_flag"],
                    nearest_code,
                    nearest_km,
                    q["occurred_at"],
                ),
            )
            inserted += 1
    return inserted


def run_seismic_sync() -> dict[str, int]:
    settings = get_settings()
    quakes = fetch_quakes()
    if not quakes:
        raise RuntimeError("USGS returned no usable earthquake features")
    with psycopg.connect(settings.psycopg_database_url) as conn:
        with conn.transaction():
            chokepoints = load_chokepoints(conn)
            count = upsert_quakes(conn, quakes, chokepoints)
    logger.info("seismic_events_upserted", extra={"count": count})
    return {"fetched": len(quakes), "rows_upserted": count}
