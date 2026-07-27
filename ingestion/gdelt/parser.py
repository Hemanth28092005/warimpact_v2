"""Parser for GDELT 2.0 Event Database tab-delimited rows."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from pydantic import ValidationError

from ingestion.common.logger import get_logger
from ingestion.gdelt.models import GDELT_EVENT_COLUMNS, RawGdeltEvent

logger = get_logger(__name__)


def parse_gdelt_csv(text: str) -> tuple[list[RawGdeltEvent], int]:
    return parse_gdelt_rows(csv.reader(StringIO(text), delimiter="\t"))


def parse_gdelt_rows(rows: Iterable[list[str]]) -> tuple[list[RawGdeltEvent], int]:
    parsed: list[RawGdeltEvent] = []
    failed = 0
    for line_number, row in enumerate(rows, start=1):
        try:
            parsed.append(parse_gdelt_row(row))
        except (ValueError, ValidationError) as exc:
            failed += 1
            logger.warning(
                "gdelt_row_skipped",
                extra={"line_number": line_number, "error": str(exc)},
            )
    return parsed, failed


def parse_gdelt_row(row: list[str]) -> RawGdeltEvent:
    if len(row) != len(GDELT_EVENT_COLUMNS):
        raise ValueError(f"expected {len(GDELT_EVENT_COLUMNS)} columns, got {len(row)}")
    values = dict(zip(GDELT_EVENT_COLUMNS, row, strict=True))
    return RawGdeltEvent(
        global_event_id=_required_int(values["global_event_id"], "global_event_id"),
        sql_date=_parse_sql_date(values["sql_date"]),
        actor1_country_code=_blank_to_none(values["actor1_country_code"]),
        actor1_type1_code=_blank_to_none(values["actor1_type1_code"]),
        actor2_country_code=_blank_to_none(values["actor2_country_code"]),
        actor2_type1_code=_blank_to_none(values["actor2_type1_code"]),
        event_code=_blank_to_none(values["event_code"]),
        event_base_code=_blank_to_none(values["event_base_code"]),
        event_root_code=_blank_to_none(values["event_root_code"]),
        quad_class=_optional_int(values["quad_class"]),
        goldstein_scale=_optional_decimal(values["goldstein_scale"]),
        num_mentions=_optional_int(values["num_mentions"]),
        num_sources=_optional_int(values["num_sources"]),
        num_articles=_optional_int(values["num_articles"]),
        avg_tone=_optional_decimal(values["avg_tone"]),
        action_geo_country_code=_blank_to_none(values["action_geo_country_code"]),
        action_geo_lat=_optional_decimal(values["action_geo_lat"]),
        action_geo_long=_optional_decimal(values["action_geo_long"]),
        date_added=_parse_date_added(values["date_added"]),
        source_url=_blank_to_none(values["source_url"]),
    )


def _blank_to_none(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _required_int(value: str, field_name: str) -> int:
    if not value.strip():
        raise ValueError(f"{field_name} is required")
    return int(value)


def _optional_int(value: str) -> int | None:
    return int(value) if value.strip() else None


def _optional_decimal(value: str) -> Decimal | None:
    return Decimal(value) if value.strip() else None


def _parse_sql_date(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def _parse_date_added(value: str) -> datetime | None:
    if not value.strip():
        return None
    return datetime.strptime(value, "%Y%m%d%H%M%S")


if __name__ == "__main__":
    print("GDELT parser ready")
