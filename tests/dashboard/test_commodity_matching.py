"""Unit and integration tests for Commodity News Matching and Atomic Snapshots."""

import pytest
from models.commodities.news import (
    COMMODITY_RULES,
    match_commodity_candidate,
    update_commodity_news,
)


def test_positive_commodity_matches():
    """Verify explicit alias and inclusion matches across major commodity categories."""
    # 1. Crude Petroleum
    is_m, conf, reason = match_commodity_candidate(
        "PETROLEUM_CRUDE",
        headline="OPEC+ Agrees to Extend Voluntary Crude Oil Production Cuts",
        url="https://reuters.com/markets/commodities/crude-cuts-2026",
    )
    assert is_m
    assert conf >= 0.80

    # 2. Natural Gas LNG
    is_m, conf, reason = match_commodity_candidate(
        "LNG_NATURAL_GAS",
        headline="India Inks 10-Year LNG Import Contract with QatarEnergy",
        url="https://economictimes.com/industry/energy/lng-import-deal",
    )
    assert is_m
    assert conf >= 0.80

    # 3. Gold
    is_m, conf, reason = match_commodity_candidate(
        "GOLD",
        headline="India Gold Import Duty Cut Triggers Surge in Bullion Imports",
        url="https://business-standard.com/markets/gold-import-duty-surge",
    )
    assert is_m
    assert conf >= 0.80

    # 4. Fertilizers
    is_m, conf, reason = match_commodity_candidate(
        "FERTILIZERS",
        headline="Government Approves Fresh Neem Coated Urea Import Subsidy Package",
        url="https://thehindubusinessline.com/agri-business/urea-subsidy-approval",
    )
    assert is_m
    assert conf >= 0.80


def test_commodity_exclusion_rules():
    """Verify that unrelated stories (smart glasses, celebrity gossip, crime) are strictly rejected."""
    # Case 1: Smart glasses / consumer electronics
    is_m, conf, _ = match_commodity_candidate(
        "PETROLEUM_CRUDE",
        headline="Meta Unveils Next-Gen AI Smart Glasses with Enhanced Battery",
        url="https://techcrunch.com/gadgets/meta-smart-glasses",
    )
    assert not is_m, "Smart glasses story must not match crude petroleum!"

    # Case 2: Celebrity gold jewelry theft
    is_m, conf, _ = match_commodity_candidate(
        "GOLD",
        headline="Hollywood Actress Wins Golden Globe Award at Star-Studded Ceremony",
        url="https://variety.com/awards/golden-globe-winners",
    )
    assert not is_m, "Golden Globe award must not match unwrought gold!"

    # Case 3: Edible oil vs crude petroleum confusion
    is_m, conf, _ = match_commodity_candidate(
        "PETROLEUM_CRUDE",
        headline="Government Slashes Import Duty on Crude Palm Oil and Sunflower Oil",
        url="https://reuters.com/markets/commodities/crude-palm-oil-duty",
    )
    assert not is_m, "Crude palm oil must not match crude petroleum!"


def test_energy_commodity_disambiguation():
    """Verify generic energy articles are not assigned across multiple commodities without evidence."""
    generic_energy_story = "Global Energy Prices Surge Amid Middle East Regional Escalation"

    # Should not match coal without coal-specific keywords
    is_coal, _, _ = match_commodity_candidate(
        "COAL_COKE",
        headline=generic_energy_story,
        url="https://bloomberg.com/energy/surge",
    )
    assert not is_coal, "Generic energy story must not match coal without specific keywords."

    # Should not match LNG without LNG keywords
    is_lng, _, _ = match_commodity_candidate(
        "LNG_NATURAL_GAS",
        headline=generic_energy_story,
        url="https://bloomberg.com/energy/surge",
    )
    assert not is_lng, "Generic energy story must not match LNG without specific keywords."
