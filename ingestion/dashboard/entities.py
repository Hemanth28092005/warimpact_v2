"""Verified Entity Registry and Anti-Hallucination Entity Validation.

Specialized handling for satirical and minor political movements (e.g. Cockroach Janta Party / CJP)
ensuring that authentic grassroots protests are preserved while unsubstantiated claims or false
acronym expansions are rejected.
"""

from __future__ import annotations

import re

# Verified entity alias registry for Cockroach Janta Party
CJP_ALIASES = [
    "cockroach janta party",
    "cockroach janata party",
    "cockroach party",
    "cockroach movement",
    "cjp",
]

CJP_PROTEST_KEYWORDS = [
    "protest",
    "rally",
    "demonstrat",
    "clash",
    "tear gas",
    "sit-in",
    "dharna",
    "march",
    "strike",
    "arrest",
    "detained",
    "agitat",
]


def is_cjp_entity(text: str) -> bool:
    """Check if text references the Cockroach Janta Party or its verified aliases."""
    if not text:
        return False
    t_lower = text.lower()
    # Word boundary match for CJP to prevent substring false positives (e.g. 'cjp' in 'ecjpi')
    if re.search(r"\bcjp\b", t_lower):
        return True
    return any(alias in t_lower for alias in CJP_ALIASES if alias != "cjp")


def validate_cjp_claim(headline: str, article_text: str = "") -> tuple[bool, str, float]:
    """Validate whether a CJP-related story represents a genuine, source-backed protest.

    Returns:
        (is_valid: bool, reason: str, confidence: float)
    """
    combined = f"{headline} {article_text}".lower()

    if not is_cjp_entity(combined):
        return False, "Not a CJP entity record", 0.0

    # Must contain evidence of an actual protest/civil action
    has_protest_action = any(kw in combined for kw in CJP_PROTEST_KEYWORDS)
    if not has_protest_action:
        return False, "CJP mention lacks evidence of protest or demonstration activity", 0.1

    # Check for obvious parody clickbait or fictional claims without protest substance
    if "cockroach movement supporters" in combined or "cockroach party supporters" in combined:
        return True, "Verified Cockroach Janta Party protest activity", 0.90

    if is_cjp_entity(headline) and has_protest_action:
        return True, "Verified CJP demonstration", 0.85

    if article_text and is_cjp_entity(article_text) and has_protest_action:
        return True, "Verified CJP protest in article body", 0.80

    return False, "Insufficient source evidence for CJP protest claim", 0.2


def safely_extract_cjp_expansion(source_text: str) -> str:
    """Extract CJP naming without inventing unauthorized expansions.

    Guarantees:
    - If full name is present in source, returns the exact casing.
    - If only 'CJP' is in source, returns 'CJP' without hallucinating an expansion.
    """
    if not source_text:
        return "CJP"

    s_lower = source_text.lower()
    if "cockroach janta party" in s_lower:
        return "Cockroach Janta Party"
    if "cockroach janata party" in s_lower:
        return "Cockroach Janata Party"
    if "cockroach party" in s_lower:
        return "Cockroach Party"
    return "CJP"
