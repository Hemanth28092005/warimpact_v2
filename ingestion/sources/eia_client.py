"""EIA (U.S. Energy Information Administration) API v2 Client.

Handles:
- Environment-based credentials (EIA_API_KEY).
- Querying https://api.eia.gov/v2/{route} for energy commodities (Petroleum, Natural Gas, Coal).
- Storing observations in `commodity_market_observations` table.
- Best-effort, non-gating market corroboration.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any
import httpx
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

EIA_BASE_URL = "https://api.eia.gov/v2"


class EIAClient:
    """EIA API v2 client for energy market observations."""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.eia_api_key
        self.base_url = EIA_BASE_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch_petroleum_spot_prices(self, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch spot prices for Brent and WTI crude."""
        if not self.is_configured:
            logger.info("EIA_API_KEY not configured; skipping EIA fetch.")
            return []

        url = f"{self.base_url}/petroleum/pri/spt/data/"
        params = {
            "api_key": self.api_key,
            "frequency": "daily",
            "data[0]": "value",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": limit,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(url, params=params)
                if r.status_code == 200:
                    return r.json().get("response", {}).get("data", [])
                logger.warning(f"EIA API petroleum returned HTTP {r.status_code}")
                return []
        except Exception as err:
            logger.error(f"Failed to query EIA petroleum API: {err}")
            return []

    def fetch_natural_gas_prices(self, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch spot/future prices for Henry Hub natural gas."""
        if not self.is_configured:
            return []

        url = f"{self.base_url}/natural-gas/pri/fut/data/"
        params = {
            "api_key": self.api_key,
            "frequency": "daily",
            "data[0]": "value",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": limit,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(url, params=params)
                if r.status_code == 200:
                    return r.json().get("response", {}).get("data", [])
                return []
        except Exception as err:
            logger.error(f"Failed to query EIA natural gas API: {err}")
            return []


def sync_eia_observations(db_url: str) -> int:
    """Fetch EIA market observations and store into commodity_market_observations."""
    client = EIAClient()
    if not client.is_configured:
        return 0

    records = client.fetch_petroleum_spot_prices(limit=30)
    records.extend(client.fetch_natural_gas_prices(limit=30))

    if not records:
        return 0

    inserted_count = 0
    now_utc = datetime.now(timezone.utc)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for r in records:
                series_desc = (r.get("series-description") or r.get("product-name") or "").lower()
                period_str = r.get("period")
                val = r.get("value")
                unit = r.get("units") or "USD/bbl"

                if not period_str or val is None:
                    continue

                try:
                    obs_date = datetime.strptime(period_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                if "brent" in series_desc or "wti" in series_desc:
                    commodity_code = "PETROLEUM_CRUDE"
                elif "gas" in series_desc:
                    commodity_code = "LNG_NATURAL_GAS"
                else:
                    continue

                series_id = r.get("series") or r.get("process") or f"eia_{commodity_code.lower()}"

                cur.execute(
                    """
                    INSERT INTO commodity_market_observations (
                        source_name, series_id, commodity_code, observation_date,
                        frequency, value, unit, retrieved_at, source_url
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_name, series_id, observation_date)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        retrieved_at = EXCLUDED.retrieved_at;
                    """,
                    (
                        "eia",
                        series_id,
                        commodity_code,
                        obs_date,
                        "daily",
                        float(val),
                        unit,
                        now_utc,
                        "https://www.eia.gov/opendata/",
                    ),
                )
                inserted_count += 1

                # Provenance
                payload_str = json.dumps(r, sort_keys=True)
                payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
                cur.execute(
                    """
                    INSERT INTO source_provenance (
                        source_name, source_record_id, publication_date,
                        evidence_role, payload_hash, raw_payload, entity_type, entity_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_name, source_record_id, entity_type)
                    DO UPDATE SET
                        retrieved_at = NOW(),
                        payload_hash = EXCLUDED.payload_hash,
                        raw_payload = EXCLUDED.raw_payload;
                    """,
                    (
                        "eia",
                        f"{series_id}_{obs_date}",
                        obs_date,
                        "corroborating_benchmark",
                        payload_hash,
                        payload_str,
                        "commodity_observation",
                        f"{commodity_code}_{obs_date}",
                    ),
                )

        conn.commit()

    return inserted_count
