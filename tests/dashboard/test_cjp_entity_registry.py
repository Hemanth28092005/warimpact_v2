"""Regression tests for Verified Entity Registry (Cockroach Janta Party / CJP)."""

import pytest
from ingestion.dashboard.entities import (
    is_cjp_entity,
    validate_cjp_claim,
    safely_extract_cjp_expansion,
)


def test_valid_cjp_protest_coverage_retention():
    """Verify that authentic CJP protest reports are preserved with high confidence."""
    headline = "Police Fire Tear Gas at Cockroach Movement Supporters in Haridwar"
    article_text = "Security forces in Haridwar clashed with hundreds of Cockroach Janta Party demonstrators holding a protest rally outside the secretariat."
    
    assert is_cjp_entity(headline)
    assert is_cjp_entity(article_text)
    
    is_valid, reason, conf = validate_cjp_claim(headline, article_text)
    assert is_valid is True
    assert conf >= 0.80
    assert "Verified" in reason


def test_unsupported_cjp_claim_quarantine():
    """Verify that CJP mentions without protest or civil action are rejected."""
    headline = "Cockroach Janta Party releases party anthem on social media"
    article_text = "The satirical youth wing launched a music video on YouTube today."
    
    is_valid, reason, conf = validate_cjp_claim(headline, article_text)
    assert is_valid is False
    assert conf < 0.50
    assert "lacks evidence of protest" in reason


def test_acronym_expansion_guard():
    """Verify that 'CJP' is not expanded into hallucinated expansions when only 'CJP' is in source."""
    # Case 1: Only acronym in source
    source_acronym_only = "Protesters affiliated with CJP gathered at Jantar Mantar demanding policy reforms."
    expansion = safely_extract_cjp_expansion(source_acronym_only)
    assert expansion == "CJP"  # Must NOT hallucinate 'Citizens for Justice and Peace' or anything else

    # Case 2: Full expansion present in source
    source_full = "Members of the Cockroach Janta Party (CJP) staged a dharna."
    expansion_full = safely_extract_cjp_expansion(source_full)
    assert expansion_full == "Cockroach Janta Party"


def test_title_source_disagreement_rejection():
    """Verify that irrelevant news with false CJP title keyword is rejected if body shows non-protest."""
    headline = "Cockroach found in restaurant kitchen causes panic"
    article_text = "Food safety officials inspected the local dining hall after a customer complaint about pest hygiene."
    
    is_valid, reason, conf = validate_cjp_claim(headline, article_text)
    assert is_valid is False
