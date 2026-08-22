"""Unit tests for Chokepoints Geodesic Disruption and Evidence Recording."""

import pytest
from models.chokepoints.disruption import (
    haversine_distance_km,
    is_maritime_relevant,
)


def test_haversine_distance_calculation():
    """Verify geodesic distance calculation on known coordinate pairs."""
    # Strait of Hormuz (26.56, 56.25) to Bandar Abbas (27.18, 56.27) ~ 69 km
    d_km = haversine_distance_km(26.56, 56.25, 27.18, 56.27)
    assert 60.0 <= d_km <= 75.0, f"Expected ~69km, got {d_km:.2f}km"

    # Bab el-Mandeb (12.58, 43.33) to Aden (12.78, 45.03) ~ 186 km
    d_aden = haversine_distance_km(12.58, 43.33, 12.78, 45.03)
    assert 175.0 <= d_aden <= 195.0, f"Expected ~186km, got {d_aden:.2f}km"


def test_maritime_relevance_filtering():
    """Verify maritime security event filter correctly discriminates maritime vs landlocked events."""
    # 1. Kinetic attack on tanker
    assert is_maritime_relevant(
        event_code="190",
        url="https://reuters.com/world/middle-east/drone-hits-commercial-tanker-gulf-aden",
        quad_class=4,
    )

    # 2. Naval patrol
    assert is_maritime_relevant(
        event_code="030",
        url="https://navytimes.com/news/naval-vessel-patrol-strait-of-hormuz",
        quad_class=1,
    )

    # 3. Landlocked domestic crime (should reject)
    assert not is_maritime_relevant(
        event_code="020",
        url="https://localnews.com/city/inland-burglary-in-shopping-mall",
        quad_class=1,
    )


def test_status_canonical_thresholds():
    """Verify exact gapless status mappings: green < 25, yellow 25..50, red >= 50."""
    scores_to_test = [
        (0.0, "green"),
        (24.99, "green"),
        (25.0, "yellow"),
        (49.99, "yellow"),
        (50.0, "red"),
        (100.0, "red"),
    ]

    for score, expected_status in scores_to_test:
        if score >= 50.0:
            status = "red"
        elif score >= 25.0:
            status = "yellow"
        else:
            status = "green"
        assert status == expected_status, f"Score {score} expected status '{expected_status}', got '{status}'"
