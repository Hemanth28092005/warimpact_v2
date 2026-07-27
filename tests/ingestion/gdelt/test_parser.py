from ingestion.gdelt.models import GDELT_EVENT_COLUMNS
from ingestion.gdelt.parser import parse_gdelt_rows, parse_gdelt_row


def make_row(global_event_id: str = "1001", sql_date: str = "20260727") -> list[str]:
    row = [""] * len(GDELT_EVENT_COLUMNS)
    values = {
        "global_event_id": global_event_id,
        "sql_date": sql_date,
        "actor1_country_code": "US",
        "actor1_type1_code": "GOV",
        "actor2_country_code": "IN",
        "actor2_type1_code": "BUS",
        "event_code": "042",
        "event_base_code": "04",
        "event_root_code": "04",
        "quad_class": "1",
        "goldstein_scale": "1.9",
        "num_mentions": "10",
        "num_sources": "3",
        "num_articles": "4",
        "avg_tone": "-2.25",
        "action_geo_country_code": "US",
        "action_geo_lat": "38.8951",
        "action_geo_long": "-77.0364",
        "date_added": "20260727000000",
        "source_url": "https://example.com/story",
    }
    for key, value in values.items():
        row[GDELT_EVENT_COLUMNS.index(key)] = value
    return row


def test_parse_gdelt_row_maps_selected_fields() -> None:
    parsed = parse_gdelt_row(make_row())

    assert parsed.global_event_id == 1001
    assert parsed.event_code == "042"
    assert parsed.num_mentions == 10
    assert parsed.source_url == "https://example.com/story"


def test_parse_gdelt_rows_skips_malformed_without_crashing() -> None:
    parsed, failed = parse_gdelt_rows([make_row(), ["bad"]])

    assert len(parsed) == 1
    assert failed == 1
