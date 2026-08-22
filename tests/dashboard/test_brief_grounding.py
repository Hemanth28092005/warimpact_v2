"""Tests for Anti-Hallucination Brief Grounding and Entity Verification.

Verifies:
1. The actual CJP regression case (rejects hallucinated 'Chief Justice of Pakistan' when source refers to citizen organization).
2. Synthetic entity expansion rejections (rejects ungrounded acronym expansions or introduced foreign actors).
3. Valid acronym expansion acceptance (accepts entity expansion when verbatim present in source text).
4. Deterministic template fallback generation and metadata attribution ('llm_grounded' vs 'template_fallback').
5. Granular protest geography hierarchy resolution.
"""

import pytest
from ingestion.dashboard.llm_filter import (
    verify_brief_grounding,
    validate_headline_relevance,
    resolve_event_location,
    extract_proper_nouns_and_acronyms,
    generate_template_fallback_brief,
)


def test_cjp_regression_rejection():
    """Verify that hallucinated expansion 'Chief Justice of Pakistan' is rejected when source only has 'CJP'."""
    source_headline = "CJP Founder Abhijeet Dipke Leads Protest March in Mumbai"
    source_snippet = "Citizen organization CJP held a peaceful demonstration in Mumbai today."
    source_combined = f"{source_headline} {source_snippet}"

    # Hallucinated brief with false expansion
    hallucinated_brief = "Chief Justice of Pakistan Abhijeet Dipke led a protest march in Mumbai."
    is_grounded = verify_brief_grounding(hallucinated_brief, source_combined)
    assert not is_grounded, "Hallucinated acronym expansion 'Chief Justice of Pakistan' should be rejected!"

    # Grounded brief using original entity
    grounded_brief = "CJP founder Abhijeet Dipke led a protest demonstration in Mumbai."
    assert verify_brief_grounding(grounded_brief, source_combined), "Grounded brief should pass verification."


def test_synthetic_entity_expansion_rejections():
    """Verify that briefs introducing foreign entities or invented expansions are rejected."""
    # Case 1: Invented foreign institution
    source_1 = "MEA Announces New Trade Framework with ASEAN Partners in New Delhi"
    hallucinated_1 = "Ministry of External Affairs signed a trade agreement with the European Union Commission."
    assert not verify_brief_grounding(hallucinated_1, source_1), "Introduced entity 'European Union Commission' should fail grounding."

    # Case 2: Invented geographical location
    source_2 = "Farmers Union Stages Sit-In Protest at Shambhu Border"
    hallucinated_2 = "Farmers Union staged a massive demonstration in Islamabad yesterday."
    assert not verify_brief_grounding(hallucinated_2, source_2), "Introduced location 'Islamabad' should fail grounding."


def test_valid_acronym_expansion_acceptance():
    """Verify that entity expansions explicitly present in source text pass grounding."""
    source_text = "The Ministry of External Affairs (MEA) confirmed the schedule for the upcoming summit."
    grounded_brief = "The Ministry of External Affairs (MEA) confirmed the official schedule for the summit."
    assert verify_brief_grounding(grounded_brief, source_text), "Verbatim acronym expansion present in source must be accepted."


def test_template_fallback_generation():
    """Verify deterministic template fallback generation."""
    brief_govt = generate_template_fallback_brief("government_actions", "Cabinet Approves New Semiconductor Subsidies")
    assert "Cabinet Approves New Semiconductor Subsidies" in brief_govt
    assert "Official government policy" in brief_govt

    brief_protest = generate_template_fallback_brief("protests", "Youth Congress Staged Rally Outside Parliament")
    assert "Youth Congress Staged Rally Outside Parliament" in brief_protest
    assert "Civil demonstration" in brief_protest


def test_granular_protest_geography_resolution():
    """Verify location resolver correctly separates venue, city, state, and country level."""
    # 1. Venue level (Jantar Mantar)
    name, level, city, state, country = resolve_event_location(None, None, url="", headline="Protestors gathered at Jantar Mantar today")
    assert name == "Jantar Mantar"
    assert level == "venue"
    assert city == "New Delhi"
    assert state == "Delhi"
    assert country == "IND"

    # 2. City level (Mumbai)
    name, level, city, state, country = resolve_event_location(19.07, 72.87, url="/city/mumbai/news", headline="Dock workers strike in Mumbai")
    assert name == "Mumbai"
    assert level == "city"
    assert city == "Mumbai"
    assert state == "Maharashtra"
    assert country == "IND"

    # 3. State level (Punjab Regional)
    name, level, city, state, country = resolve_event_location(None, None, url="", headline="Punjab state-wide transport strike called")
    assert name == "Punjab"
    assert level == "state"
    assert city is None
    assert state == "Punjab"
    assert country == "IND"

    # 4. National fallback
    name, level, city, state, country = resolve_event_location(None, None, url="", headline="Nationwide bank employees union agitation")
    assert name == "India"
    assert level == "national"
    assert city is None
    assert state is None
    assert country == "IND"
