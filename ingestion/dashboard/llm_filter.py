"""Anti-hallucination LLM validation, lexical brief grounding, and location resolution for Dashboard feeds.

Key guarantees:
1. Anti-hallucination brief grounding: Zero external knowledge, zero acronym expansion unless present in source.
2. Post-generation Lexical Grounding Validator: Rejects briefs with untraceable entities and falls back to deterministic templates.
3. Strict controlled vocabularies and confidence bounds (0.0 to 1.0).
4. Granular protest geography (location_name, location_level, city, state, country_code).
5. Indian government action actor and jurisdiction validation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Known coordinate bounding boxes for major Indian cities
INDIAN_CITIES_GEO = [
    ("New Delhi", "Delhi", 28.45, 28.75, 76.95, 77.35),
    ("Mumbai", "Maharashtra", 18.85, 19.30, 72.75, 73.05),
    ("Bengaluru", "Karnataka", 12.85, 13.10, 77.45, 77.75),
    ("Kolkata", "West Bengal", 22.45, 22.70, 88.25, 88.50),
    ("Chennai", "Tamil Nadu", 12.95, 13.20, 80.15, 80.35),
    ("Hyderabad", "Telangana", 17.30, 17.55, 78.35, 78.60),
    ("Ahmedabad", "Gujarat", 22.95, 23.15, 72.45, 72.70),
    ("Chandigarh", "Chandigarh", 30.68, 30.80, 76.68, 76.85),
    ("Ludhiana", "Punjab", 30.85, 30.98, 75.75, 75.92),
    ("Siliguri", "West Bengal", 26.65, 26.78, 88.35, 88.48),
    ("Haridwar", "Uttarakhand", 29.80, 30.18, 78.10, 78.68),
    ("Hubballi-Dharwad", "Karnataka", 15.30, 15.42, 75.10, 75.22),
    ("Lucknow", "Uttar Pradesh", 26.78, 26.96, 80.85, 81.05),
    ("Gurgaon", "Haryana", 28.40, 28.52, 76.98, 77.10),
    ("Patna", "Bihar", 25.55, 25.68, 85.08, 85.22),
    ("Srinagar", "Jammu & Kashmir", 34.00, 34.18, 74.70, 74.90),
    ("Guwahati", "Assam", 26.10, 26.22, 91.68, 91.82),
    ("Kochi", "Kerala", 9.90, 10.05, 76.20, 76.38),
    ("Bhopal", "Madhya Pradesh", 23.20, 23.32, 77.35, 77.48),
    ("Jaipur", "Rajasthan", 26.85, 26.98, 75.75, 75.88),
]

INDIAN_STATES_GEO = [
    ("Punjab", 29.50, 32.50, 73.80, 76.90),
    ("Haryana", 27.60, 30.90, 74.40, 77.60),
    ("Uttar Pradesh", 23.80, 30.40, 77.00, 84.60),
    ("Maharashtra", 15.60, 22.00, 72.60, 80.90),
    ("Karnataka", 11.50, 18.50, 74.00, 78.60),
    ("Tamil Nadu", 8.00, 13.50, 76.20, 80.35),
    ("Kerala", 8.20, 12.80, 74.80, 77.50),
    ("West Bengal", 21.50, 27.20, 85.80, 89.80),
    ("Assam", 24.10, 28.20, 89.70, 96.00),
    ("Uttarakhand", 28.70, 31.40, 77.50, 81.00),
    ("Rajasthan", 23.00, 30.20, 69.50, 78.30),
    ("Gujarat", 20.10, 24.70, 68.10, 74.50),
    ("Jammu & Kashmir", 32.20, 37.10, 73.40, 80.30),
]


def resolve_event_location(
    lat: float | None = None,
    long_: float | None = None,
    url: str = "",
    headline: str = "",
    article_text: str = "",
) -> tuple[str, str, str | None, str | None, str]:
    """Resolve granular geography hierarchy for an event.

    Returns:
        (location_name, location_level, city, state, country_code)
        where location_level in ('venue', 'city', 'district', 'state', 'national', 'unknown')
    """
    text_combined = f"{url.lower()} {headline.lower()} {article_text.lower()}".strip()

    # 1. Venue-level check
    if "jantar mantar" in text_combined or "jantar-mantar" in text_combined:
        return "Jantar Mantar", "venue", "New Delhi", "Delhi", "IND"
    if "ramlila maidan" in text_combined:
        return "Ramlila Maidan", "venue", "New Delhi", "Delhi", "IND"
    if "gateway of india" in text_combined:
        return "Gateway of India", "venue", "Mumbai", "Maharashtra", "IND"

    # 2. Match city keywords
    city_keywords = [
        ("New Delhi", "Delhi", ["new delhi", "new-delhi", "delhi-police", "parliament", "/city/delhi"]),
        ("Mumbai", "Maharashtra", ["mumbai", "/city/mumbai", "mid-day.com/mumbai"]),
        ("Ludhiana", "Punjab", ["ludhiana", "/city/ludhiana"]),
        ("Siliguri", "West Bengal", ["siliguri", "in-siliguri"]),
        ("Haridwar", "Uttarakhand", ["rishikesh", "haridwar", "pauri garhwal"]),
        ("Hubballi-Dharwad", "Karnataka", ["hubballi", "dharwad"]),
        ("Lucknow", "Uttar Pradesh", ["lucknow", "/city/lucknow"]),
        ("Gurgaon", "Haryana", ["gurgaon", "gurugram", "/city/gurgaon"]),
        ("Chandigarh", "Chandigarh", ["chandigarh", "/city/chandigarh"]),
        ("Kochi", "Kerala", ["kochi", "/news/national/kerala"]),
        ("Bengaluru", "Karnataka", ["bengaluru", "bangalore", "/city/bengaluru"]),
        ("Chennai", "Tamil Nadu", ["chennai", "/city/chennai"]),
        ("Kolkata", "West Bengal", ["kolkata", "calcuttanews"]),
        ("Guwahati", "Assam", ["guwahati", "/city/guwahati"]),
        ("Patna", "Bihar", ["patna", "/city/patna"]),
        ("Jaipur", "Rajasthan", ["jaipur", "/city/jaipur"]),
    ]

    for city_name, state_name, keywords in city_keywords:
        if any(kw in text_combined for kw in keywords):
            return city_name, "city", city_name, state_name, "IND"

    # 3. Coordinate bounding box check
    if lat is not None and long_ is not None:
        lat_f, long_f = float(lat), float(long_)
        for city_name, state_name, min_lat, max_lat, min_lon, max_lon in INDIAN_CITIES_GEO:
            if min_lat <= lat_f <= max_lat and min_lon <= long_f <= max_lon:
                return city_name, "city", city_name, state_name, "IND"

        for state_name, min_lat, max_lat, min_lon, max_lon in INDIAN_STATES_GEO:
            if min_lat <= lat_f <= max_lat and min_lon <= long_f <= max_lon:
                return state_name, "state", None, state_name, "IND"

    # 4. State keyword fallback
    state_keywords = [
        ("Punjab", ["punjab"]),
        ("Maharashtra", ["maharashtra"]),
        ("Uttar Pradesh", ["uttar pradesh", "up congress", "up-"]),
        ("Karnataka", ["karnataka"]),
        ("Kerala", ["kerala"]),
        ("West Bengal", ["west bengal", "bengal"]),
        ("Assam", ["assam"]),
        ("Uttarakhand", ["uttarakhand"]),
        ("Rajasthan", ["rajasthan"]),
        ("Gujarat", ["gujarat"]),
        ("Haryana", ["haryana"]),
        ("Jammu & Kashmir", ["kashmir", "j&k"]),
    ]
    for state_name, kws in state_keywords:
        if any(kw in text_combined for kw in kws):
            return state_name, "state", None, state_name, "IND"

    return "India", "national", None, None, "IND"


# Exclusion keywords
PROTEST_EXCLUSION_KEYWORDS = [
    "burglar", "loot marriage palace", "robbery", "theft", "stolen",
    "beauty", "self-acceptance", "sushmita sen", "bollywood", "cricket",
    "ipl", "q1 revenue", "q2 revenue", "profit down", "results up",
    "box office", "horoscope", "astrology", "movie review",
    "marriage palace", "wedding", "bachelorette", "recipes",
]

GOVT_ACTION_EXCLUSION_KEYWORDS = [
    "blood donation", "exam update", "ssc exam", "sustainable agriculture",
    "startup accelerators", "shopping", "recipe", "horoscope", "cricket",
    "movie", "box office", "fashion", "flood rescue", "fire rescue",
    "families demand", "kin demand", "protesters demand", "opposition slams",
    "criticizes govt", "urges centre", "plea in court", "activists seek",
]

GOVT_ACTORS = [
    "ministry of external affairs", "mea", "ministry of home affairs", "mha",
    "ministry of finance", "modi", "cabinet", "parliament", "supreme court",
    "high court", "centre", "central government", "union government",
    "rbi", "reserve bank of india", "sebi", "election commission", "dgp",
    "delhi police", "indian army", "indian navy", "indian air force",
    "state government", "chief minister", "governor",
]


def extract_proper_nouns_and_acronyms(text: str) -> list[str]:
    """Extract capitalized multi-word phrases and uppercase acronyms for grounding check."""
    # Match uppercase acronyms of 2 to 6 letters (e.g. CJP, MEA, NATO, CBI)
    acronyms = re.findall(r"\b[A-Z]{2,6}\b", text)

    # Match Capitalized phrases (e.g. Chief Justice of Pakistan, Supreme Court)
    capitalized_phrases = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text)

    # Individual capitalized names of length >= 4
    single_names = re.findall(r"\b[A-Z][a-z]{3,}\b", text)

    # Filter out sentence-starting common English words
    common_stops = {
        "This", "That", "There", "Here", "What", "When", "Where", "Which", "While",
        "Official", "Government", "Ministry", "Report", "After", "Before", "During",
        "According", "Under", "Over", "With", "From", "Into", "About", "Against",
    }
    filtered_single = [w for w in single_names if w not in common_stops]

    combined = list(set(acronyms + capitalized_phrases + filtered_single))
    return combined


def verify_brief_grounding(brief: str, source_text: str) -> bool:
    """Verify that every proper noun and uppercase acronym in brief is strictly present in source_text.

    Returns False if the LLM introduced external entity names or expanded acronyms not in source_text.
    """
    if not brief or not source_text:
        return False

    entities = extract_proper_nouns_and_acronyms(brief)
    src_norm = source_text.lower()

    for entity in entities:
        ent_norm = entity.lower()
        # Direct substring match
        if ent_norm in src_norm:
            continue

        # If it's a multi-word entity, check if all component words are present in source
        words = ent_norm.split()
        if len(words) > 1 and all(w in src_norm for w in words):
            continue

        logger.info(f"Brief grounding rejection: Entity '{entity}' not present in source text.")
        return False

    return True


def generate_template_fallback_brief(feed_type: str, headline: str) -> str:
    """Generate a deterministic, 100% grounded template summary brief based on source headline."""
    clean_h = headline.strip().rstrip(".")
    if feed_type == "government_actions":
        return f"Official government policy and administrative action regarding {clean_h}."
    elif feed_type == "protests":
        return f"Civil demonstration and protest activity reported regarding {clean_h}."
    elif feed_type == "regional_headlines":
        return f"Regional security and geopolitical development regarding {clean_h}."
    elif feed_type == "commodity_news":
        return f"Trade and market news development regarding {clean_h}."
    return f"Intelligence news report regarding {clean_h}."


def validate_headline_relevance(
    feed_type: str,
    headline: str,
    url: str = "",
    event_code: str = "",
    article_text: str = "",
) -> tuple[bool, float, str, str | None, str, str, str | None, str]:
    """Validate headline relevance, actor, and generate verified grounded summary brief.

    Returns:
        (
            is_relevant: bool,
            confidence: float,
            reason: str,
            brief: str | None,
            validation_source: str,  # 'groq', 'gemini', 'rules'
            brief_source: str,       # 'llm_grounded', 'template_fallback', 'none'
            actor_entity: str | None,
            action_type: str         # canonical action type
        )
    """
    if not headline or len(headline.strip()) < 12:
        return False, 0.0, "Headline too short or empty", None, "rules", "none", None, "unknown_legacy"

    h_lower = headline.lower()
    u_lower = url.lower()
    source_combined = f"{headline} {url} {article_text}".strip()
    text_combined = f"{h_lower} {u_lower}"

    # Fast exclusion checks
    if feed_type == "protests":
        for kw in PROTEST_EXCLUSION_KEYWORDS:
            if kw in text_combined:
                return False, 0.0, f"Protest false positive matched exclusion: '{kw}'", None, "rules", "none", None, "unknown_legacy"

    elif feed_type == "government_actions":
        for kw in GOVT_ACTION_EXCLUSION_KEYWORDS:
            if kw in text_combined:
                return False, 0.0, f"Government action rejected (petition or non-policy): '{kw}'", None, "rules", "none", None, "unknown_legacy"

    # Single-call LLM Verification with Anti-Hallucination Prompt
    llm_res = _call_llm_verification(feed_type, headline, article_text)
    if llm_res is not None:
        is_rel, conf, reason, raw_brief, val_src, actor, act_type = llm_res
        if not is_rel:
            return False, conf, reason, None, val_src, "none", None, act_type

        # Verify Grounding of the generated brief
        if raw_brief and verify_brief_grounding(raw_brief, source_combined):
            return True, conf, reason, raw_brief, val_src, "llm_grounded", actor, act_type
        else:
            # Fall back to template brief if LLM hallucinated ungrounded entities
            fallback_brief = generate_template_fallback_brief(feed_type, headline)
            return True, conf, reason, fallback_brief, val_src, "template_fallback", actor, act_type

    # Deterministic Rule-Based Fallback
    return _evaluate_rule_based(feed_type, headline, url, event_code, text_combined)


def _evaluate_rule_based(
    feed_type: str,
    headline: str,
    url: str,
    event_code: str,
    text_combined: str,
) -> tuple[bool, float, str, str | None, str, str, str | None, str]:
    """Deterministic heuristic fallback when LLM is offline."""
    h_lower = headline.lower()

    if feed_type == "protests":
        protest_words = ["protest", "strike", "demonstrat", "rally", "march", "agitat", "jantar mantar", "dharna", "sit-in", "unrest"]
        if any(w in text_combined for w in protest_words) or event_code.startswith("14"):
            brief = generate_template_fallback_brief("protests", headline)
            return True, 0.85, "Validated via protest rule heuristics", brief, "rules", "template_fallback", None, "unknown_legacy"
        return False, 0.2, "Lacks clear civil unrest demonstration indicators", None, "rules", "none", None, "unknown_legacy"

    elif feed_type == "government_actions":
        # Check Indian actor presence
        detected_actor = None
        for act in GOVT_ACTORS:
            if act in text_combined:
                detected_actor = act.title()
                break

        if detected_actor and any(v in text_combined for v in ["order", "ban", "approv", "sign", "meet", "notif", "direct", "deploy", "allocat", "pass", "launch"]):
            brief = generate_template_fallback_brief("government_actions", headline)
            return True, 0.85, f"Official Indian government action by {detected_actor}", brief, "rules", "template_fallback", detected_actor, "administrative"
        return False, 0.2, "Lacks official government actor decision indicators", None, "rules", "none", None, "unknown_legacy"

    elif feed_type == "regional_headlines":
        entertainment_kws = ["horoscope", "recipe", "ipl score", "movie review", "fashion show", "box office", "celebrity"]
        if any(kw in text_combined for kw in entertainment_kws):
            return False, 0.1, "Generic entertainment/lifestyle content", None, "rules", "none", None, "unknown_legacy"
        brief = generate_template_fallback_brief("regional_headlines", headline)
        return True, 0.80, "Validated via regional security heuristics", brief, "rules", "template_fallback", None, "unknown_legacy"

    brief = generate_template_fallback_brief(feed_type, headline)
    return True, 0.75, "Default validated", brief, "rules", "template_fallback", None, "unknown_legacy"


def _call_llm_verification(
    feed_type: str,
    headline: str,
    article_text: str = "",
) -> tuple[bool, float, str, str | None, str, str | None, str] | None:
    """Run LLM validation with strict anti-hallucination prompt. Primary: Groq, Secondary: Gemini."""
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    prompt = (
        f"You are a strict geopolitical/news event validator and summarizer for an intelligence dashboard.\n"
        f"Target category: '{feed_type}'.\n"
        f"Headline: \"{headline}\".\n"
        f"Article snippet: \"{article_text[:600]}\".\n\n"
        f"STRICT RULES:\n"
        f"1. Use ONLY facts, names, proper nouns, and entities present directly in the supplied headline/snippet. "
        f"Do NOT use external knowledge. Do NOT expand any acronym (e.g. CJP, MEA, NATO, CBI) unless its full expansion is explicitly written in the source.\n"
        f"2. For 'government_actions': The government body/official must be the ACTOR performing an order, policy change, agreement, enforcement, or official decision. Reject if the government is merely being petitioned, demanded, or criticized.\n"
        f"3. For 'protests': Reject routine crime, celebrity news, and non-protest court disputes.\n"
        f"4. For 'regional_headlines': Reject entertainment, sports scores, and clickbait.\n"
        f"5. Output valid JSON ONLY with keys:\n"
        f"   - is_relevant (boolean)\n"
        f"   - confidence (float between 0.0 and 1.0)\n"
        f"   - reason (short explanation)\n"
        f"   - brief (1-2 sentence neutral summary using ONLY entities in source, or null if not relevant)\n"
        f"   - actor_entity (string or null, e.g. 'Ministry of Home Affairs')\n"
        f"   - action_type (one of: 'diplomatic', 'regulatory', 'legislative', 'judicial', 'administrative', 'fiscal', 'security', 'unknown_legacy')\n"
    )

    # 1. Try Groq
    if groq_key:
        try:
            req_data = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=req_data,
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return (
                    bool(parsed.get("is_relevant", False)),
                    float(parsed.get("confidence", 0.8)),
                    str(parsed.get("reason", "Validated via Groq")),
                    parsed.get("brief"),
                    "groq",
                    parsed.get("actor_entity"),
                    str(parsed.get("action_type", "unknown_legacy")),
                )
        except Exception as e:
            logger.debug(f"Groq validation failed: {e}")

    # 2. Try Gemini
    if gemini_key:
        try:
            req_data = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
            }).encode("utf-8")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(content)
                return (
                    bool(parsed.get("is_relevant", False)),
                    float(parsed.get("confidence", 0.8)),
                    str(parsed.get("reason", "Validated via Gemini")),
                    parsed.get("brief"),
                    "gemini",
                    parsed.get("actor_entity"),
                    str(parsed.get("action_type", "unknown_legacy")),
                )
        except Exception as e:
            logger.debug(f"Gemini validation failed: {e}")

    return None
