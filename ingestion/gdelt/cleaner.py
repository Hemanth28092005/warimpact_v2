"""Cleaner for parsed GDELT events."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast

import pycountry

from ingestion.common.logger import get_logger
from ingestion.gdelt.models import CleanGdeltEvent, RawGdeltEvent

logger = get_logger(__name__)

MIN_GDELT_DATE = date(1979, 1, 1)

FIPS_TO_ISO3 = {
    "AF": "AFG",
    "CH": "CHN",
    "IN": "IND",
    "IR": "IRN",
    "IS": "ISR",
    "PK": "PAK",
    "RS": "RUS",
    "SA": "SAU",
    "UK": "GBR",
    "US": "USA",
    "UP": "UKR",
}


def clean_events(raw_events: list[RawGdeltEvent]) -> tuple[list[CleanGdeltEvent], int]:
    seen: set[int] = set()
    cleaned: list[CleanGdeltEvent] = []
    failed = 0
    for raw_event in raw_events:
        try:
            if raw_event.global_event_id in seen:
                continue
            seen.add(raw_event.global_event_id)
            cleaned.append(clean_event(raw_event))
        except ValueError as exc:
            failed += 1
            logger.warning(
                "gdelt_event_rejected",
                extra={"global_event_id": raw_event.global_event_id, "error": str(exc)},
            )
    return cleaned, failed


def clean_event(raw_event: RawGdeltEvent) -> CleanGdeltEvent:
    if raw_event.sql_date < MIN_GDELT_DATE:
        raise ValueError("event_date predates GDELT coverage floor")
    if raw_event.sql_date > datetime.now(UTC).date():
        raise ValueError("event_date is in the future")

    return CleanGdeltEvent(
        global_event_id=raw_event.global_event_id,
        event_date=raw_event.sql_date,
        event_code=raw_event.event_code,
        event_base_code=raw_event.event_base_code,
        event_root_code=raw_event.event_root_code,
        quad_class=raw_event.quad_class,
        goldstein_scale=raw_event.goldstein_scale,
        num_mentions=raw_event.num_mentions,
        num_sources=raw_event.num_sources,
        num_articles=raw_event.num_articles,
        avg_tone=raw_event.avg_tone,
        actor1_country_code=normalize_country_code(raw_event.actor1_country_code),
        actor2_country_code=normalize_country_code(raw_event.actor2_country_code),
        actor1_type=raw_event.actor1_type1_code,
        actor2_type=raw_event.actor2_type1_code,
        action_geo_lat=raw_event.action_geo_lat,
        action_geo_long=raw_event.action_geo_long,
        action_geo_country_code=normalize_country_code(raw_event.action_geo_country_code),
        source_url=raw_event.source_url,
        has_missing_actors=not raw_event.actor1_country_code or not raw_event.actor2_country_code,
    )


def normalize_country_code(code: str | None) -> str | None:
    if not code:
        return None
    normalized = code.strip().upper()
    if len(normalized) == 3:
        return normalized
    if normalized in FIPS_TO_ISO3:
        return FIPS_TO_ISO3[normalized]
    country = pycountry.countries.get(alpha_2=normalized)
    if country:
        return cast(str, country.alpha_3)
    return None


if __name__ == "__main__":
    print("GDELT cleaner ready")
