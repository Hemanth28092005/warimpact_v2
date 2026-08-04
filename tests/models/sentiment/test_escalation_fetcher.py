"""Unit and integration tests for escalation_fetcher module."""

from __future__ import annotations

import pytest
from models.sentiment.escalation_fetcher import (
    ALL_TARGET_COUNTRIES,
    REGION_COUNTRY_MAPPING,
    fetch_escalation_article_text,
)
from models.sentiment.scorer import compute_composite_historical_sentiment


def test_region_country_mappings() -> None:
    """Verify target region country lists match expected 38-scope countries."""
    assert "IND" in REGION_COUNTRY_MAPPING["india"]
    assert "USA" in REGION_COUNTRY_MAPPING["usa"]
    assert set(REGION_COUNTRY_MAPPING["europe"]) == {"GBR", "FRA", "DEU", "ITA", "ESP", "UKR"}
    assert set(REGION_COUNTRY_MAPPING["middle_east"]) == {"ISR", "TUR", "SAU", "SYR", "YEM"}

    assert len(ALL_TARGET_COUNTRIES) == 13
    assert "IND" in ALL_TARGET_COUNTRIES
    assert "ISR" in ALL_TARGET_COUNTRIES


def test_severity_formula_consistency() -> None:
    """Confirm severity formula matches aggression score composite sentiment."""
    # Material Conflict (quad_class=4 -> -1.0), tone=-8.0 -> -0.8, goldstein=-10.0 -> -1.0
    # severity = 0.4*(-0.8) + 0.4*(-1.0) + 0.2*(-1.0) = -0.32 - 0.4 - 0.2 = -0.92 <= -0.5
    sev = compute_composite_historical_sentiment(avg_tone=-8.0, goldstein_scale=-10.0, quad_class=4)
    assert sev <= -0.5
    assert sev == -0.92

    # Material Cooperation (quad_class=2 -> +1.0), tone=5.0 -> +0.5, goldstein=7.0 -> +0.7
    # severity = 0.4*(0.5) + 0.4*(0.7) + 0.2*(1.0) = +0.68 > -0.5
    coop_sev = compute_composite_historical_sentiment(avg_tone=5.0, goldstein_scale=7.0, quad_class=2)
    assert coop_sev > -0.5


@pytest.mark.asyncio
async def test_escalation_fetcher_execution() -> None:
    """Test running escalation article fetcher across trailing window."""
    summary = await fetch_escalation_article_text(lookback_minutes=20)
    assert summary.lookback_minutes == 20
    assert summary.matched_events_count >= 0
    assert summary.unique_urls_count >= 0
