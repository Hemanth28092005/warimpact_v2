"""Unit tests verifying protest geography resolution and non-degenerate multi-factor severity scoring."""

from datetime import date
import pytest
from ingestion.dashboard.tasks import calculate_protest_severity
from ingestion.dashboard.llm_filter import resolve_event_location


def test_protest_severity_calculation():
    """Verify that protest severity calculation produces dynamic, non-constant scores across scenarios."""
    ref_date = date(2026, 8, 22)

    # 1. High severity: Strike with clashes and high mentions
    sev_high = calculate_protest_severity(
        event_code="145",  # Strike
        headline="Transport Workers Strike in Mumbai: Clashes with Police and Multiple Arrests",
        num_mentions=40,
        avg_tone=-8.5,
        event_date=date(2026, 8, 20),
        ref_date=ref_date,
    )
    assert sev_high >= 75.0, f"Expected high severity >= 75, got {sev_high}"

    # 2. Medium severity: Peaceful sit-in protest
    sev_med = calculate_protest_severity(
        event_code="141",  # Demonstration
        headline="Youth Congress Holds Peaceful Dharna at Jantar Mantar",
        num_mentions=10,
        avg_tone=-2.0,
        event_date=date(2026, 8, 18),
        ref_date=ref_date,
    )
    assert 40.0 <= sev_med <= 75.0, f"Expected medium severity 40-75, got {sev_med}"

    # 3. Low baseline severity: Small localized rally
    sev_low = calculate_protest_severity(
        event_code="140",  # Unspecified demonstration
        headline="Local Residents Hold Small Rally Demanding Road Repairs",
        num_mentions=2,
        avg_tone=0.5,
        event_date=date(2026, 8, 5),  # Older event
        ref_date=ref_date,
    )
    assert sev_low <= 45.0, f"Expected lower severity <= 45, got {sev_low}"
    assert sev_low < sev_med < sev_high, "Severity should scale monotonically with conflict intensity"


def test_protest_geography_hierarchy():
    """Verify venue, city, state, and national geography distinctions."""
    # Venue
    name, level, city, state, country = resolve_event_location(None, None, url="", headline="Protest at Jantar Mantar in New Delhi")
    assert level == "venue"
    assert city == "New Delhi"
    assert country == "IND"

    # City
    name, level, city, state, country = resolve_event_location(22.57, 88.36, url="/city/kolkata", headline="Doctors hold rally in Kolkata")
    assert level == "city"
    assert city == "Kolkata"
    assert state == "West Bengal"

    # State
    name, level, city, state, country = resolve_event_location(None, None, url="", headline="Karnataka state transport corporation strike")
    assert level == "state"
    assert city is None
    assert state == "Karnataka"
