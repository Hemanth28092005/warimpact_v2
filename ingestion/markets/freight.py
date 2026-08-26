"""Container freight index snapshots for major east-west trade lanes.

Uses explicitly labeled estimated rates seeded from published weekly index
readings (Drewry WCI / Freightos FBX methodology). Rows carry
is_estimated=true and data_source='manual_seed' until a licensed provider
key is configured. When FREIGHTOS_FBX_URL is set, live FBX values override
the seed for matching lane codes.
"""

from __future__ import annotations

import logging
from datetime import date, timezone, datetime
from typing import Any

import httpx
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

FREIGHT_LANES: list[dict[str, Any]] = [
    {"code": "WCI_SHANGHAI_ROTTERDAM", "name": "Shanghai > Rotterdam", "rate_usd": 3200.0},
    {"code": "WCI_SHANGHAI_LA", "name": "Shanghai > Los Angeles", "rate_usd": 2400.0},
    {"code": "WCI_SHANGHAI_NY", "name": "Shanghai > New York", "rate_usd": 3400.0},
    {"code": "WCI_ROTTERDAM_NY", "name": "Rotterdam > New York", "rate_usd": 1500.0},
    {"code": "WCI_LA_SHANGHAI", "name": "Los Angeles > Shanghai", "rate_usd": 900.0},
]

DATA_SOURCE = "manual_seed"


def fetch_live_fbx(url: str, timeout_seconds: float = 10.0) -> dict[str, float]:
    response = httpx.get(url, timeout=timeout_seconds, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    lanes: dict[str, float] = {}
    for entry in payload if isinstance(payload, list) else payload.get("data", []):
        code = entry.get("laneCode") or entry.get("code")
        rate = entry.get("rateUsd") or entry.get("rate")
        if isinstance(code, str) and isinstance(rate, (int, float)):
            lanes[code.upper()] = float(rate)
    return lanes


def upsert_freight_indices(conn: psycopg.Connection, readings: list[dict[str, Any]]) -> int:
    inserted = 0
    today = date.today()
    with conn.cursor() as cur:
        for r in readings:
            prev = r["rate_usd"]
            cur.execute(
                """
                SELECT rate_usd FROM freight_indices
                WHERE index_code = %s AND data_source = %s
                ORDER BY rate_date DESC LIMIT 1
                """,
                (r["index_code"], r["data_source"]),
            )
            prior = cur.fetchone()
            if prior is not None:
                prev = float(prior[0])
            change = ((r["rate_usd"] - prev) / prev * 100.0) if prev else None
            cur.execute(
                """
                INSERT INTO freight_indices
                    (index_code, name, rate_usd, previous_rate_usd, change_pct, unit_label,
                     route_label, rate_date, data_source, is_estimated, source_citation)
                VALUES (%s, %s, %s, %s, %s, 'per FEU', %s, %s, %s, %s, %s)
                ON CONFLICT (index_code, rate_date, data_source) DO UPDATE SET
                    rate_usd = EXCLUDED.rate_usd,
                    previous_rate_usd = EXCLUDED.previous_rate_usd,
                    change_pct = EXCLUDED.change_pct
                """,
                (
                    r["index_code"],
                    r["name"],
                    r["rate_usd"],
                    prev if prior is not None else None,
                    change,
                    r["name"],
                    today,
                    r["data_source"],
                    r.get("is_estimated", True),
                    r.get("source_citation"),
                ),
            )
            inserted += 1
    return inserted


def run_freight_sync() -> dict[str, int]:
    import os

    settings = get_settings()
    readings: list[dict[str, Any]] = []
    for lane in FREIGHT_LANES:
        readings.append(
            {
                "index_code": lane["code"],
                "name": lane["name"],
                "rate_usd": lane["rate_usd"],
                "data_source": DATA_SOURCE,
                "is_estimated": True,
                "source_citation": "Seeded estimate aligned to published Drewry WCI / Freightos FBX weekly methodology",
            }
        )

    live_url = os.getenv("FREIGHTOS_FBX_URL", "").strip()
    live_count = 0
    if live_url:
        try:
            live_lanes = fetch_live_fbx(live_url)
            for lane in FREIGHT_LANES:
                rate = live_lanes.get(lane["code"].upper())
                if rate is not None:
                    readings.append(
                        {
                            "index_code": lane["code"],
                            "name": lane["name"],
                            "rate_usd": rate,
                            "data_source": "freightos_fbx",
                            "is_estimated": False,
                            "source_citation": "Freightos Baltic Index live feed",
                        }
                    )
                    live_count += 1
        except Exception as exc:
            logger.warning("fbx_live_fetch_failed", extra={"error": str(exc)})

    with psycopg.connect(settings.psycopg_database_url) as conn:
        with conn.transaction():
            count = upsert_freight_indices(conn, readings)

    logger.info("freight_indices_upserted", extra={"count": count, "live": live_count})
    return {"rows_upserted": count, "live_rows": live_count}
