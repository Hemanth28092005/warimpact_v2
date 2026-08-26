"""ACLED (Armed Conflict Location & Event Data) Client and Protest Mapping Engine.

Handles:
- Environment-based credentials (ACLED_EMAIL, ACLED_ACCESS_KEY).
- Feature-flagged availability (graceful fallback if access/approval is not configured).
- Official REST endpoint (https://acleddata.com/api/acled/read), JSON format.
- Normalized protest geography mapping:
  - location -> location_name
  - admin1 -> state; admin2/admin3 -> additional context
  - city -> derived only when location is a genuine city-level place per geo_precision
  - country -> country_code ('IND')
- Multi-factor severity scoring driven by sub_event_type, fatalities, and tags.
- Grounded notes extraction for anti-hallucination LLM brief generation.
- Provenance recording into source_provenance table.
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

ACLED_BASE_URL = "https://acleddata.com/api/acled/read"
ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"

KNOWN_INDIAN_METROS = {
    "new delhi", "delhi", "mumbai", "bengaluru", "bangalore", "hyderabad",
    "chennai", "kolkata", "pune", "ahmedabad", "jaipur", "lucknow",
    "chandigarh", "bhopal", "patna", "ranchi", "guwahati", "shimla",
    "dehradun", "srinagar", "jammu", "thiruvananthapuram", "kochi",
    "visakhapatnam", "bhubaneswar", "surat", "nagpur", "indore",
}


class ACLEDClient:
    """Official ACLED REST API client with OAuth2 and direct key support."""

    _cached_token: str | None = None
    _token_expires_at: float = 0.0

    def __init__(
        self,
        email: str | None = None,
        access_key: str | None = None,
        base_url: str = ACLED_BASE_URL,
        token_url: str = ACLED_TOKEN_URL,
    ) -> None:
        settings = get_settings()
        self.email = email if email is not None else settings.acled_email
        self.access_key = access_key if access_key is not None else settings.acled_access_key
        self.base_url = base_url
        self.token_url = token_url

    @property
    def is_configured(self) -> bool:
        """Check if ACLED credentials are fully configured in the environment."""
        return bool(self.email and self.access_key)

    def get_access_token(self, timeout_seconds: float = 15.0) -> str | None:
        """Retrieve OAuth2 Bearer access token using username/password grant."""
        if not self.is_configured:
            return None

        now = datetime.now(timezone.utc).timestamp()
        if self._cached_token and now < self._token_expires_at - 60:
            return self._cached_token

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WarImpactPlatform/1.0",
        }
        data = {
            "username": self.email,
            "password": self.access_key,
            "grant_type": "password",
            "client_id": "acled",
            "scope": "authenticated",
        }

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                resp = client.post(self.token_url, headers=headers, data=data)
                if resp.status_code == 200:
                    token_data = resp.json()
                    ACLEDClient._cached_token = token_data.get("access_token")
                    expires_in = float(token_data.get("expires_in", 86400))
                    ACLEDClient._token_expires_at = now + expires_in
                    logger.info("Successfully acquired ACLED OAuth2 access token.")
                    return ACLEDClient._cached_token
                else:
                    logger.warning(f"ACLED OAuth token error: HTTP {resp.status_code} {resp.text[:200]}")
        except Exception as err:
            logger.warning(f"Failed to acquire ACLED OAuth token: {err}")

        return None

    def fetch_protest_events(
        self,
        country: str = "India",
        limit: int = 500,
        since_date: date | str | None = None,
        timeout_seconds: float = 20.0,
    ) -> list[dict[str, Any]]:
        """Fetch raw protest records from official ACLED endpoint using Bearer token or direct key."""
        if not self.is_configured:
            logger.info("ACLED credentials not set; feature flag inactive.")
            return []

        fields = (
            "event_id_cnty|event_date|country|admin1|admin2|admin3|location|"
            "latitude|longitude|geo_precision|event_type|sub_event_type|"
            "interaction|fatalities|notes|tags|timestamp"
        )

        params: dict[str, Any] = {
            "_format": "json",
            "country": country,
            "event_type": "Protests",
            "limit": limit,
            "fields": fields,
        }
        if since_date:
            params["event_date"] = str(since_date)
            params["event_date_where"] = ">="

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WarImpactPlatform/1.0",
            "Content-Type": "application/json",
        }

        # Attempt 1: OAuth2 Bearer Token
        token = self.get_access_token(timeout_seconds=timeout_seconds)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                resp = client.get(self.base_url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        return data.get("data", [])
                    elif isinstance(data, list):
                        return data

                # Attempt 2: Direct key query fallback
                if resp.status_code in {401, 403}:
                    logger.info("Retrying ACLED query with direct email & key parameters...")
                    legacy_params = dict(params)
                    legacy_params["email"] = self.email
                    legacy_params["key"] = self.access_key
                    resp2 = client.get(self.base_url, params=legacy_params, headers={"User-Agent": headers["User-Agent"]})
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        return data2.get("data", []) if isinstance(data2, dict) else data2
                    else:
                        logger.warning(f"ACLED API returned HTTP {resp2.status_code}: {resp2.text[:200]}")
                        return []

                logger.warning(f"ACLED API returned HTTP {resp.status_code}: {resp.text[:200]}")
                return []
        except Exception as err:
            logger.error(f"Failed to query ACLED API: {err}")
            return []


def calculate_acled_severity(
    sub_event_type: str | None,
    fatalities: int | float | None,
    tags: str | None = None,
) -> float:
    """Calculate normalized protest severity [0.0, 100.0] from ACLED event taxonomy and fatalities."""
    sub_type = (sub_event_type or "").lower().strip()
    fat_count = float(fatalities or 0)
    tag_str = (tags or "").lower()

    if "excessive force" in sub_type or "excessive force" in tag_str:
        base_score = 65.0
    elif "violent demonstration" in sub_type or "mob violence" in sub_type:
        base_score = 60.0
    elif "protest with intervention" in sub_type or "tear gas" in tag_str:
        base_score = 45.0
    elif "peaceful protest" in sub_type:
        base_score = 25.0
    else:
        base_score = 30.0

    # Fatalities drive non-linear upward severity
    fatality_adder = min(35.0, fat_count * 10.0)

    # Tag escalations
    if "strike" in tag_str or "bandh" in tag_str:
        base_score += 5.0
    if "clash" in tag_str or "weapons" in tag_str:
        base_score += 10.0

    return max(5.0, min(100.0, base_score + fatality_adder))


COUNTRY_ISO_MAP = {
    "india": "IND",
    "bangladesh": "BGD",
    "pakistan": "PAK",
    "nepal": "NPL",
    "sri lanka": "LKA",
    "maldives": "MDV",
    "myanmar": "MMR",
    "afghanistan": "AFG",
    "china": "CHN",
    "united states": "USA",
    "israel": "ISR",
    "ukraine": "UKR",
    "russia": "RUS",
    "yemen": "YEM",
    "syria": "SYR",
}


def map_acled_record_to_protest(raw_record: dict[str, Any]) -> dict[str, Any]:
    """Map raw ACLED record (individual event or weekly aggregation) to database schema."""
    loc_raw = raw_record.get("location") or raw_record.get("admin1") or ""
    admin1 = raw_record.get("admin1") or ""
    admin2 = raw_record.get("admin2") or ""
    admin3 = raw_record.get("admin3") or ""
    geo_prec = int(raw_record.get("geo_precision") or 1)
    notes = raw_record.get("notes") or ""
    event_id = raw_record.get("event_id_cnty") or ""

    country_raw = (raw_record.get("country") or "India").strip()
    country_code = COUNTRY_ISO_MAP.get(country_raw.lower(), "IND")

    location_name = loc_raw.strip() if loc_raw else f"{country_raw} (National)"
    state = admin1.strip() if admin1 else None

    # Handle special venues (e.g. Jantar Mantar, Azad Maidan, Ramlila Maidan)
    loc_lower = location_name.lower()
    if "jantar mantar" in loc_lower:
        city = "New Delhi"
        state = state or "Delhi"
        location_level = "venue"
    elif "azad maidan" in loc_lower:
        city = "Mumbai"
        state = state or "Maharashtra"
        location_level = "venue"
    elif "ramlila maidan" in loc_lower:
        city = "New Delhi"
        state = state or "Delhi"
        location_level = "venue"
    elif geo_prec == 1 and loc_lower in KNOWN_INDIAN_METROS:
        city = location_name
        location_level = "city"
    elif geo_prec == 1 and admin2 and loc_lower != admin1.lower():
        city = location_name
        location_level = "city"
    elif geo_prec == 2:
        city = None
        location_level = "district"
    elif geo_prec == 3 or not state:
        city = None
        location_level = "state"
    else:
        city = location_name if loc_lower in KNOWN_INDIAN_METROS else None
        location_level = "city" if city else "state"

    # Latitude / Longitude fallback to centroid coordinates
    lat_val = raw_record.get("latitude") if raw_record.get("latitude") is not None else raw_record.get("centroid_latitude")
    lng_val = raw_record.get("longitude") if raw_record.get("longitude") is not None else raw_record.get("centroid_longitude")
    
    def _to_float(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    def _to_int(v: Any) -> int:
        f = _to_float(v)
        return int(f) if f is not None else 0

    lat = _to_float(lat_val)
    lng = _to_float(lng_val)
    fatalities = _to_int(raw_record.get("fatalities"))
    sub_event_type = raw_record.get("sub_event_type") or raw_record.get("event_type") or "Protest"
    event_count = max(1, _to_int(raw_record.get("events")))
    pop_exposure = str(raw_record.get("population_exposure") or "").strip()

    severity = calculate_acled_severity(sub_event_type, fatalities, raw_record.get("tags"))
    if event_count > 10:
        severity = min(100.0, severity + 10.0)
    elif event_count > 3:
        severity = min(100.0, severity + 5.0)

    event_date = raw_record.get("event_date") or raw_record.get("week")

    # Headline derivation
    if notes:
        headline = notes.split(".")[0].strip()
    elif event_count > 1:
        headline = f"{event_count} {sub_event_type} demonstrations in {location_name}"
    else:
        headline = f"{sub_event_type} in {location_name}"
    if len(headline) > 255:
        headline = headline[:252] + "..."

    # Grounded neutral brief
    if notes:
        brief = notes
    else:
        pop_clause = f" with population exposure of {pop_exposure}" if pop_exposure and pop_exposure != "0" else ""
        brief = f"ACLED registered {event_count} {sub_event_type} event(s) across {location_name}, {country_raw}{pop_clause}."
    if len(brief) > 400:
        brief = brief[:397] + "..."

    if not event_id:
        safe_sub = sub_event_type.replace(" ", "_").lower()
        event_id = f"acled_{event_date}_{country_code.lower()}_{location_name.replace(' ', '_').lower()}_{safe_sub}"

    payload_str = json.dumps(raw_record, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    return {
        "source_record_id": str(event_id),
        "event_date": str(event_date) if event_date else None,
        "location_name": location_name,
        "location_level": location_level,
        "state": state,
        "city": city,
        "country_code": country_code,
        "action_geo_lat": lat,
        "action_geo_long": lng,
        "event_severity": severity,
        "headline": headline,
        "llm_brief": brief,
        "validation_source": "acled",
        "brief_source": "llm_grounded" if notes else "template_fallback",
        "confidence": 0.95,
        "source_url": f"https://acleddata.com/data-export-tool/?event_id={event_id}",
        "raw_payload": raw_record,
        "payload_hash": payload_hash,
    }


def record_acled_provenance(
    conn: psycopg.Connection,
    protest_id: int,
    mapped_item: dict[str, Any],
) -> None:
    """Record provenance row for ACLED event into source_provenance table."""
    with conn.cursor() as cur:
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
                "acled",
                mapped_item.get("source_url"),
                mapped_item.get("source_record_id"),
                mapped_item.get("event_date"),
                "primary_feed",
                mapped_item.get("payload_hash"),
                json.dumps(mapped_item.get("raw_payload")),
                "protest",
                str(protest_id),
            ),
        )


def ingest_acled_events_into_db(raw_events: list[dict[str, Any]], db_url: str) -> int:
    """Ingest a list of raw ACLED event dictionaries into protests and source_provenance tables."""
    if not raw_events:
        return 0

    inserted_count = 0
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for raw in raw_events:
                mapped = map_acled_record_to_protest(raw)
                cur.execute(
                    """
                    INSERT INTO protests (
                        city, location_name, location_level, state, country_code,
                        event_date, headline, action_geo_lat, action_geo_long,
                        event_severity, llm_brief, validation_source, brief_source,
                        confidence, source_url, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (city, event_date, headline) DO UPDATE
                    SET location_name = EXCLUDED.location_name,
                        location_level = EXCLUDED.location_level,
                        state = EXCLUDED.state,
                        country_code = EXCLUDED.country_code,
                        action_geo_lat = EXCLUDED.action_geo_lat,
                        action_geo_long = EXCLUDED.action_geo_long,
                        event_severity = EXCLUDED.event_severity,
                        llm_brief = EXCLUDED.llm_brief,
                        validation_source = 'acled',
                        brief_source = EXCLUDED.brief_source,
                        confidence = EXCLUDED.confidence,
                        source_url = EXCLUDED.source_url,
                        updated_at = NOW()
                    RETURNING id;
                    """,
                    (
                        mapped["city"] or mapped["location_name"],
                        mapped["location_name"],
                        mapped["location_level"],
                        mapped["state"],
                        mapped["country_code"],
                        mapped["event_date"],
                        mapped["headline"],
                        mapped["action_geo_lat"],
                        mapped["action_geo_long"],
                        mapped["event_severity"],
                        mapped["llm_brief"],
                        "acled",
                        mapped["brief_source"],
                        mapped["confidence"],
                        mapped["source_url"],
                    ),
                )
                row = cur.fetchone()
                if row:
                    record_acled_provenance(conn, row[0], mapped)
                    inserted_count += 1
        conn.commit()

    return inserted_count


def ingest_acled_csv_file(csv_path: str, db_url: str) -> int:
    """Ingest an exported ACLED CSV file into protests and source_provenance tables."""
    import csv

    events: list[dict[str, Any]] = []
    with open(csv_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append(dict(row))

    return ingest_acled_events_into_db(events, db_url)
