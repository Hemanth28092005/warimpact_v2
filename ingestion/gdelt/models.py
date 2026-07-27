"""Pydantic models for the GDELT 2.0 Event Database export schema.

The GDELT 2.0 event export contains 61 tab-delimited columns. Phase 1 keeps the
fields needed for `gdelt_events` and documents the remaining columns as dropped
for now rather than treating them as unknown data.

Dropped columns in Phase 1:
Actor1Code, Actor1Name, Actor1KnownGroupCode, Actor1EthnicCode,
Actor1Religion1Code, Actor1Religion2Code, Actor2Code, Actor2Name,
Actor2KnownGroupCode, Actor2EthnicCode, Actor2Religion1Code,
Actor2Religion2Code, IsRootEvent, actor geography detail beyond country,
action geography detail beyond country/lat/long, DATEADDED, and
ActionGeo_FullName are dropped until later analytical phases need them.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

GDELT_EVENT_COLUMNS: tuple[str, ...] = (
    "global_event_id",
    "sql_date",
    "month_year",
    "year",
    "fraction_date",
    "actor1_code",
    "actor1_name",
    "actor1_country_code",
    "actor1_known_group_code",
    "actor1_ethnic_code",
    "actor1_religion1_code",
    "actor1_religion2_code",
    "actor1_type1_code",
    "actor1_type2_code",
    "actor1_type3_code",
    "actor2_code",
    "actor2_name",
    "actor2_country_code",
    "actor2_known_group_code",
    "actor2_ethnic_code",
    "actor2_religion1_code",
    "actor2_religion2_code",
    "actor2_type1_code",
    "actor2_type2_code",
    "actor2_type3_code",
    "is_root_event",
    "event_code",
    "event_base_code",
    "event_root_code",
    "quad_class",
    "goldstein_scale",
    "num_mentions",
    "num_sources",
    "num_articles",
    "avg_tone",
    "actor1_geo_type",
    "actor1_geo_full_name",
    "actor1_geo_country_code",
    "actor1_geo_adm1_code",
    "actor1_geo_adm2_code",
    "actor1_geo_lat",
    "actor1_geo_long",
    "actor1_geo_feature_id",
    "actor2_geo_type",
    "actor2_geo_full_name",
    "actor2_geo_country_code",
    "actor2_geo_adm1_code",
    "actor2_geo_adm2_code",
    "actor2_geo_lat",
    "actor2_geo_long",
    "actor2_geo_feature_id",
    "action_geo_type",
    "action_geo_full_name",
    "action_geo_country_code",
    "action_geo_adm1_code",
    "action_geo_adm2_code",
    "action_geo_lat",
    "action_geo_long",
    "action_geo_feature_id",
    "date_added",
    "source_url",
)


class RawGdeltEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    global_event_id: int
    sql_date: date
    actor1_country_code: str | None
    actor1_type1_code: str | None
    actor2_country_code: str | None
    actor2_type1_code: str | None
    event_code: str | None
    event_base_code: str | None
    event_root_code: str | None
    quad_class: int | None
    goldstein_scale: Decimal | None
    num_mentions: int | None
    num_sources: int | None
    num_articles: int | None
    avg_tone: Decimal | None
    action_geo_country_code: str | None
    action_geo_lat: Decimal | None
    action_geo_long: Decimal | None
    date_added: datetime | None
    source_url: str | None


class CleanGdeltEvent(BaseModel):
    global_event_id: int
    event_date: date
    event_code: str | None
    event_base_code: str | None
    event_root_code: str | None
    quad_class: int | None
    goldstein_scale: Decimal | None
    num_mentions: int | None
    num_sources: int | None
    num_articles: int | None
    avg_tone: Decimal | None
    actor1_country_code: str | None
    actor2_country_code: str | None
    actor1_type: str | None
    actor2_type: str | None
    action_geo_lat: Decimal | None
    action_geo_long: Decimal | None
    action_geo_country_code: str | None
    source_url: str | None
    has_missing_actors: bool
    is_synthetic: bool = False


if __name__ == "__main__":
    print(len(GDELT_EVENT_COLUMNS))
