"""Unit tests for 30-commodity taxonomy coverage and rule completeness."""

import pytest
from scripts.seed_dashboard_data import COMMODITIES_DATA
from models.commodities.news import COMMODITY_RULES, match_commodity_candidate


def test_complete_30_commodity_taxonomy_coverage():
    """Verify that every commodity in tracked_commodities has a complete matching rule in COMMODITY_RULES."""
    tracked_codes = {item[0] for item in COMMODITIES_DATA}
    assert len(tracked_codes) == 30, f"Expected 30 commodities in reference data, got {len(tracked_codes)}"

    rule_codes = set(COMMODITY_RULES.keys())
    assert len(rule_codes) == 30, f"Expected 30 commodity rules, got {len(rule_codes)}"

    # Exact 1-to-1 match
    assert tracked_codes == rule_codes, f"Mismatch between tracked commodities and rule keys: {tracked_codes ^ rule_codes}"

    # Verify rule structure
    for code, rule in COMMODITY_RULES.items():
        assert "aliases" in rule and len(rule["aliases"]) > 0, f"Commodity {code} missing aliases"
        assert "inclusions" in rule and len(rule["inclusions"]) > 0, f"Commodity {code} missing inclusions"
        assert "exclusions" in rule, f"Commodity {code} missing exclusions"
        assert "category" in rule, f"Commodity {code} missing category"


def test_commodity_matching_with_article_text_evidence():
    """Verify matching works with article text evidence even if title is concise."""
    code = "PETROLEUM_CRUDE"
    headline = "Energy Market Weekly Overview"
    url = "https://example.com/energy-update-august"
    article_text = "Global crude oil shipments through the Red Sea decreased as OPEC production cuts took effect, pushing Brent crude prices higher."

    is_match, conf, reason = match_commodity_candidate(code, headline, url, article_text)
    assert is_match is True
    assert conf >= 0.85
    assert "crude" in reason or "opec" in reason.lower()


def test_commodity_matching_exclusion_filtering():
    """Verify that consumer items or unrelated topics matching substring are excluded."""
    code = "PETROLEUM_CRUDE"
    headline = "Celebrity chef launches new sunflower vegetable oil brand"
    url = "https://example.com/edible-oil-launch"
    article_text = "The organic vegetable cooking oil is now available in supermarkets."

    is_match, conf, reason = match_commodity_candidate(code, headline, url, article_text)
    assert is_match is False
    assert "exclusion" in reason.lower()
