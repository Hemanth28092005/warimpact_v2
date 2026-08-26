"""data.gov.in (Open Government Data Platform India) Client.

Documented Resources & Metadata:
1. Ministry of Commerce & Industry - Trade Policy & Export Notices
   - Resource ID: `6176ee09-3d56-4a3b-8115-23bcbe576b11`
   - Frequency: Monthly / Notification-based
   - Licence: Open Government Data (OGD) Licence India
   - Endpoint: https://api.data.gov.in/resource/6176ee09-3d56-4a3b-8115-23bcbe576b11
2. Ministry of Petroleum & Natural Gas - Production, Consumption & Trade
   - Resource ID: `5c2f62fe-5afa-4119-a499-fec4d604d5d0`
   - Frequency: Monthly
   - Licence: Open Government Data (OGD) Licence India
   - Endpoint: https://api.data.gov.in/resource/5c2f62fe-5afa-4119-a499-fec4d604d5d0
3. Ministry of Finance - Revenue & Customs Notifications
   - Resource ID: `13e5d321-7299-4c7b-9c76-9d32b55b6826`
   - Frequency: Real-time / Daily
   - Licence: Open Government Data (OGD) Licence India
   - Endpoint: https://api.data.gov.in/resource/13e5d321-7299-4c7b-9c76-9d32b55b6826
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
import httpx
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

DATAGOVIN_BASE_URL = "https://api.data.gov.in/resource"

DATASETS_METADATA = [
    {
        "resource_id": "6176ee09-3d56-4a3b-8115-23bcbe576b11",
        "ministry": "Ministry of Commerce & Industry",
        "action_type": "regulatory",
        "title": "Foreign Trade Policy and Export Promotion Notifications",
        "frequency": "Monthly",
        "licence": "OGD India",
    },
    {
        "resource_id": "5c2f62fe-5afa-4119-a499-fec4d604d5d0",
        "ministry": "Ministry of Petroleum & Natural Gas",
        "action_type": "administrative",
        "title": "Monthly Petroleum and Natural Gas Trade Data",
        "frequency": "Monthly",
        "licence": "OGD India",
    },
    {
        "resource_id": "13e5d321-7299-4c7b-9c76-9d32b55b6826",
        "ministry": "Ministry of Finance",
        "action_type": "fiscal",
        "title": "Customs Tariffs and Revenue Policy Notifications",
        "frequency": "Daily",
        "licence": "OGD India",
    },
]


class DataGovInClient:
    """Client for Open Government Data (data.gov.in) APIs."""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.datagovin_api_key
        self.base_url = DATAGOVIN_BASE_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch_resource_records(
        self,
        resource_id: str,
        limit: int = 10,
        timeout_seconds: float = 15.0,
    ) -> list[dict[str, Any]]:
        """Fetch records for a specific documented data.gov.in resource ID."""
        if not self.is_configured:
            logger.info("DATAGOVIN_API_KEY not configured; skipping data.gov.in fetch.")
            return []

        url = f"{self.base_url}/{resource_id}"
        params = {
            "api-key": self.api_key,
            "format": "json",
            "limit": limit,
        }
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("records", [])
                logger.warning(f"data.gov.in resource {resource_id} returned HTTP {resp.status_code}")
                return []
        except Exception as err:
            logger.error(f"Failed to query data.gov.in resource {resource_id}: {err}")
            return []


def sync_datagovin_provenance(db_url: str) -> int:
    """Sync documented data.gov.in datasets and record evidence in source_provenance."""
    client = DataGovInClient()
    if not client.is_configured:
        return 0

    inserted_count = 0
    now_utc = datetime.now(timezone.utc)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for meta in DATASETS_METADATA:
                res_id = meta["resource_id"]
                records = client.fetch_resource_records(res_id, limit=5)
                for idx, rec in enumerate(records, 1):
                    payload_str = json.dumps(rec, sort_keys=True)
                    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

                    cur.execute(
                        """
                        INSERT INTO source_provenance (
                            source_name, source_url, source_record_id, publication_date,
                            evidence_role, payload_hash, raw_payload, entity_type, entity_id
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (source_name, source_record_id, entity_type)
                        DO UPDATE SET
                            retrieved_at = NOW(),
                            payload_hash = EXCLUDED.payload_hash,
                            raw_payload = EXCLUDED.raw_payload;
                        """,
                        (
                            "datagovin",
                            f"{DATAGOVIN_BASE_URL}/{res_id}",
                            f"{res_id}_{idx}",
                            now_utc,
                            "corroborating_policy",
                            payload_hash,
                            payload_str,
                            "government_action",
                            f"gov_{res_id}_{idx}",
                        ),
                    )
                    inserted_count += 1

        conn.commit()

    return inserted_count
