"""Live military aircraft positions from the adsb.lol free ADS-B API.

Polls the global military feed and upserts positions keyed by ICAO hex.
Stale rows beyond the retention window are purged each run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

ADSB_MIL_URL = "https://api.adsb.lol/v2/mil"
USER_AGENT = "war-impact-platform/0.3 (geopolitical research dashboard)"
RETENTION_MINUTES = 120


def fetch_military_aircraft(timeout_seconds: float = 25.0) -> list[dict[str, Any]]:
    response = httpx.get(ADSB_MIL_URL, timeout=timeout_seconds, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    aircraft = response.json().get("ac", []) or []
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for a in aircraft:
        hex_code = str(a.get("hex") or "").strip()
        lat = a.get("lat")
        lon = a.get("lon")
        if not hex_code or lat is None or lon is None:
            continue
        alt_raw = a.get("alt_baro")
        if alt_raw == "ground":
            alt = 0
        elif isinstance(alt_raw, (int, float)):
            alt = int(alt_raw)
        else:
            alt = None
        rows.append(
            {
                "hex_code": hex_code,
                "registration": (a.get("r") or "").strip() or None,
                "aircraft_type": (a.get("t") or "").strip() or None,
                "callsign": (a.get("flight") or "").strip() or None,
                "latitude": float(lat),
                "longitude": float(lon),
                "altitude_ft": alt,
                "ground_speed_kt": float(a["gs"]) if isinstance(a.get("gs"), (int, float)) else None,
                "squawk": (str(a.get("squawk")) if a.get("squawk") is not None else None),
                "observed_at": now,
            }
        )
    return rows


def upsert_flights(conn: psycopg.Connection, flights: list[dict[str, Any]]) -> int:
    if not flights:
        return 0
    with conn.cursor() as cur:
        params = [
            (
                f["hex_code"], f["registration"], f["aircraft_type"], f["callsign"],
                f["latitude"], f["longitude"], f["altitude_ft"], f["ground_speed_kt"],
                f["squawk"], f["observed_at"],
            )
            for f in flights
        ]
        cur.executemany(
            """
            INSERT INTO military_flights
                (hex_code, registration, aircraft_type, callsign, latitude, longitude,
                 altitude_ft, ground_speed_kt, squawk, observed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hex_code) DO UPDATE SET
                registration = EXCLUDED.registration,
                aircraft_type = EXCLUDED.aircraft_type,
                callsign = EXCLUDED.callsign,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                altitude_ft = EXCLUDED.altitude_ft,
                ground_speed_kt = EXCLUDED.ground_speed_kt,
                squawk = EXCLUDED.squawk,
                observed_at = EXCLUDED.observed_at
            """,
            params,
        )
        cur.execute(
            "DELETE FROM military_flights WHERE observed_at < %s",
            (datetime.now(timezone.utc) - timedelta(minutes=RETENTION_MINUTES),),
        )
    return len(flights)


def run_flights_sync() -> dict[str, int]:
    settings = get_settings()
    flights = fetch_military_aircraft()
    if not flights:
        raise RuntimeError("adsb.lol returned no military aircraft")
    with psycopg.connect(settings.psycopg_database_url) as conn:
        with conn.transaction():
            count = upsert_flights(conn, flights)
    logger.info("military_flights_upserted", extra={"count": count})
    return {"fetched": len(flights), "rows_upserted": count}
