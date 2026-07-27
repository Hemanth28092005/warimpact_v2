import pytest

from ingestion.gdelt.parser import parse_gdelt_row
from ingestion.gdelt.cleaner import clean_event, clean_events, normalize_country_code
from tests.ingestion.gdelt.test_parser import make_row


def test_normalize_country_code_spot_checks() -> None:
    assert normalize_country_code("US") == "USA"
    assert normalize_country_code("IN") == "IND"
    assert normalize_country_code("UK") == "GBR"
    assert normalize_country_code("CH") == "CHN"
    assert normalize_country_code("RS") == "RUS"


def test_clean_event_flags_missing_actor_codes() -> None:
    row = make_row()
    row[7] = ""
    raw = parse_gdelt_row(row)

    cleaned = clean_event(raw)

    assert cleaned.has_missing_actors is True
    assert cleaned.actor1_country_code is None


def test_clean_events_dedupes_by_global_event_id() -> None:
    raw = parse_gdelt_row(make_row(global_event_id="2001"))

    cleaned, failed = clean_events([raw, raw])

    assert len(cleaned) == 1
    assert failed == 0


def test_clean_event_rejects_pre_1979_date() -> None:
    raw = parse_gdelt_row(make_row(sql_date="19780101"))

    with pytest.raises(ValueError, match="predates"):
        clean_event(raw)
