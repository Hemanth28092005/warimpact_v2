"""Commodity News Ingestion and Explicit Rule Matching Engine.

Implements explicit 30-commodity taxonomy matching with:
- Exclusion filtering (blocks consumer electronics like smart glasses, celebrity gossip, crime).
- Disambiguation (generic energy stories not assigned to specific commodities without explicit evidence).
- Staged Candidate Snapshots & Atomic Transaction Replacement (replaces ranks 1..N and clears expired snapshots).
- Persistent `news_stories` linking.
- In-memory URL caching and fast-path URL filtering to prevent redundant network I/O.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
import psycopg

from ingestion.common.config import get_settings
from ingestion.dashboard import headline_extractor
from ingestion.dashboard.llm_filter import generate_template_fallback_brief
from ingestion.dashboard.url_normalizer import normalize_url

logger = logging.getLogger(__name__)

# Complete 30-commodity rule taxonomy (Aliases, Inclusions, and Exclusions)
COMMODITY_RULES: dict[str, dict[str, Any]] = {
    # 1. Energy & Hydrocarbons
    "PETROLEUM_CRUDE": {
        "aliases": ["crude oil", "brent crude", "wti crude", "opec output", "oil tanker", "oil imports", "crude price", "crude shipment", "oil barrels"],
        "inclusions": ["opec", "crude oil", "brent", "wti", "petroleum reserves", "crude supply", "oil production cuts"],
        "exclusions": ["smart glasses", "edible oil", "cooking oil", "palm oil", "sunflower oil", "olive oil", "vegetable oil", "hair oil"],
        "category": "energy",
    },
    "PETROLEUM_PRODUCTS": {
        "aliases": ["diesel export", "petrol price", "jet fuel", "aviation turbine fuel", "refinery output", "naphtha", "fuel oil"],
        "inclusions": ["refinery run", "fuel export", "petroleum refining", "gasoil", "gasoline export"],
        "exclusions": ["edible oil", "cooking oil", "palm oil"],
        "category": "energy",
    },
    "NATURAL_GAS_LNG": {
        "aliases": ["lng import", "liquefied natural gas", "natural gas pipeline", "gas spot price", "lng tanker", "cng prices", "piped gas"],
        "inclusions": ["lng cargo", "lng terminal", "henry hub", "natural gas contract", "qatar gas"],
        "exclusions": ["tear gas", "greenhouse gas", "gas cylinder blast", "toxic gas leak"],
        "category": "energy",
    },
    "COAL_THERMAL": {
        "aliases": ["thermal coal", "coal import", "power plant coal", "coal inventory", "indonesian coal", "australian coal", "coal auction"],
        "inclusions": ["thermal coal import", "coal dispatch", "coal fired power", "coal shortage"],
        "exclusions": ["charcoal face wash", "coalition"],
        "category": "energy",
    },
    "COAL_COKING": {
        "aliases": ["coking coal", "metallurgical coal", "steelmaking coal", "hard coking coal", "met coal import"],
        "inclusions": ["blast furnace coal", "coking coal price", "met coal shipment"],
        "exclusions": ["coalition", "thermal power"],
        "category": "energy",
    },

    # 2. Precious Metals & Gems
    "GOLD_UNWROUGHT": {
        "aliases": ["gold bullion", "gold import duty", "gold reserve", "rbi gold", "spot gold", "gold sovereign", "mcx gold"],
        "inclusions": ["gold import", "bullion trade", "gold price per ounce", "central bank gold"],
        "exclusions": ["golden globe", "gold medal", "golden temple", "gold cup", "celebrity ring", "gold heist"],
        "category": "precious_metals",
    },
    "SILVER_UNWROUGHT": {
        "aliases": ["silver bullion", "silver import", "spot silver", "mcx silver", "silver bars"],
        "inclusions": ["silver import duty", "silver price", "bullion vault"],
        "exclusions": ["silver screen", "silver jubilee", "silver medal"],
        "category": "precious_metals",
    },
    "DIAMONDS_ROUGH": {
        "aliases": ["rough diamonds", "uncut diamonds", "diamond import", "surat rough diamond", "alrosa rough"],
        "inclusions": ["rough diamond shipment", "rough diamond auction", "surat diamond bursa import"],
        "exclusions": ["diamond league", "baseball diamond", "diamond jubilee", "rihanna diamond"],
        "category": "precious_metals",
    },
    "DIAMONDS_POLISHED": {
        "aliases": ["polished diamonds", "cut diamonds", "diamond export", "surat polished export", "gem and jewellery export"],
        "inclusions": ["lab grown diamond export", "polished diamond prices", "gjepc diamond export"],
        "exclusions": ["diamond league", "diamond necklace theft"],
        "category": "precious_metals",
    },

    # 3. Agriculture & Edible Oils
    "VEGETABLE_OILS_PALM": {
        "aliases": ["crude palm oil", "cpo import", "palm oil duty", "malaysian palm oil", "indonesian palm oil export"],
        "inclusions": ["palm oil import", "cpo tariff", "edible palm oil"],
        "exclusions": ["crude petroleum", "brent crude", "palm springs"],
        "category": "agriculture",
    },
    "VEGETABLE_OILS_SOYA_SUNFLOWER": {
        "aliases": ["soybean oil import", "sunflower oil cargo", "ukraine sunflower oil", "degummed soya oil", "edible oil import"],
        "inclusions": ["sunflower oil import", "soyoil shipment", "edible oil tariff"],
        "exclusions": ["petroleum", "diesel"],
        "category": "agriculture",
    },
    "WHEAT_GRAIN": {
        "aliases": ["wheat import", "wheat export ban", "wheat msp", "fci wheat auction", "wheat buffer stock", "global wheat prices"],
        "inclusions": ["wheat shipment", "wheat grain procurement", "wheat tariff"],
        "exclusions": ["wheatish complexion", "buckwheat pancake"],
        "category": "agriculture",
    },
    "RICE_NON_BASMATI": {
        "aliases": ["non basmati rice export", "parboiled rice export", "rice export ban", "white rice export quota"],
        "inclusions": ["rice export duty", "fci rice procurement", "rice shipment ban"],
        "exclusions": ["condoleezza rice", "rice university"],
        "category": "agriculture",
    },
    "RICE_BASMATI": {
        "aliases": ["basmati rice export", "basmati mrl", "basmati minimum export price", "pusa basmati"],
        "inclusions": ["basmati export", "mep on basmati", "basmati consignments"],
        "exclusions": ["rice university"],
        "category": "agriculture",
    },
    "SUGAR_RAW_WHITE": {
        "aliases": ["sugar export quota", "raw sugar import", "ethanol blending sugar", "isma sugar output", "global sugar deficit"],
        "inclusions": ["sugar mill production", "cane sugar export", "sugar export restrictions"],
        "exclusions": ["sugar mommy", "blood sugar level", "sugar daddy"],
        "category": "agriculture",
    },
    "PULSES_LENTILS": {
        "aliases": ["tur dal import", "urad dal import", "yellow pea import duty", "chana dal buffer", "masur dal shipment"],
        "inclusions": ["pulses", "lentils", "pigeon pea", "chickpea import", "dal prices"],
        "exclusions": ["pulse rate", "heart pulse"],
        "category": "agriculture",
    },
    "COTTON_RAW": {
        "aliases": ["raw cotton", "cotton export", "cotton bale", "cotton harvest", "cotton msp", "textile cotton"],
        "inclusions": ["cotton bale", "raw cotton export", "cotton lint"],
        "exclusions": ["cotton candy", "cotton buds"],
        "category": "agriculture",
    },

    # 4. Fertilizers & Chemicals
    "FERTILIZERS_UREA": {
        "aliases": ["urea import", "fertilizer subsidy", "urea shipment", "neem coated urea", "urea tender"],
        "inclusions": ["urea fertilizer", "urea imports", "urea plant"],
        "exclusions": ["blood urea"],
        "category": "fertilizers",
    },
    "FERTILIZERS_DAP": {
        "aliases": ["di-ammonium phosphate", "dap fertilizer", "dap import", "phosphate fertilizer", "dap subsidy"],
        "inclusions": ["dap fertilizer", "di-ammonium phosphate", "phosphatic fertilizer"],
        "exclusions": ["dap audio"],
        "category": "fertilizers",
    },
    "FERTILIZERS_MOP": {
        "aliases": ["muriate of potash", "mop fertilizer", "potash import", "canadian potash", "belarus potash"],
        "inclusions": ["potash", "muriate of potash", "potassic fertilizer"],
        "exclusions": ["mop and bucket", "cleaning mop"],
        "category": "fertilizers",
    },
    "ORGANIC_CHEMICALS": {
        "aliases": ["organic chemicals", "benzene trade", "toluene export", "petrochemical export", "bulk chemicals"],
        "inclusions": ["petrochemical export", "organic chemical shipment", "chemical plant output"],
        "exclusions": ["organic food", "organic farming"],
        "category": "chemicals",
    },

    # 5. Metals & Industrial Ores
    "IRON_ORE": {
        "aliases": ["iron ore export", "iron ore pellet", "iron ore fines", "iron ore lumps", "odisha iron ore", "iron ore duty"],
        "inclusions": ["iron ore", "iron pellets", "iron mining export"],
        "exclusions": ["iron man", "iron age", "steam iron"],
        "category": "metals",
    },
    "STEEL_PRODUCTS": {
        "aliases": ["finished steel", "hot rolled coil", "steel export", "steel safeguard duty", "crude steel output", "steel tariff"],
        "inclusions": ["steel export", "hrc coil", "steel rebar", "steel manufacturing output"],
        "exclusions": ["steelers", "man of steel", "steely"],
        "category": "metals",
    },
    "COPPER_REFINED": {
        "aliases": ["refined copper", "copper cathode", "copper cathode import", "copper smelter", "copper concentrate"],
        "inclusions": ["copper cathode", "copper anode", "copper bullion", "copper wire rod"],
        "exclusions": ["copper vessel", "police copper"],
        "category": "metals",
    },
    "ALUMINIUM_UNWROUGHT": {
        "aliases": ["primary aluminium", "aluminium ingot", "aluminium export", "unwrought aluminium", "aluminium smelter"],
        "inclusions": ["aluminium ingot", "aluminium export", "aluminium tariff"],
        "exclusions": ["aluminium foil packaging", "aluminium windows"],
        "category": "metals",
    },

    # 6. Electronics & Critical Components
    "ELECTRONICS_SMARTPHONES": {
        "aliases": ["smartphone export", "mobile phone export", "electronics pli scheme", "foxconn india export", "iphone export india"],
        "inclusions": ["smartphone manufacturing", "mobile phone manufacturing", "electronics export hub"],
        "exclusions": ["smartphone review", "smartphone launch event", "gaming phone review"],
        "category": "electronics",
    },
    "ELECTRONICS_INTEGRATED_CIRCUITS": {
        "aliases": ["integrated circuits", "semiconductor chip import", "semiconductor fabrication", "ic chips import", "semiconductor pli"],
        "inclusions": ["semiconductor fab", "silicon wafer", "chip fabrication", "semiconductor assembly"],
        "exclusions": ["circuit court", "f1 circuit"],
        "category": "electronics",
    },
    "SOLAR_CELLS_MODULES": {
        "aliases": ["solar cells import", "solar module tariff", "solar almm list", "photovoltaic cell import", "solar wafer"],
        "inclusions": ["solar cell", "solar pv module", "photovoltaic module import"],
        "exclusions": ["solar eclipse", "solar flare"],
        "category": "electronics",
    },
    "CRITICAL_MINERALS_LITHIUM": {
        "aliases": ["lithium import", "lithium auction", "lithium ore", "lithium battery raw material", "critical mineral block"],
        "inclusions": ["lithium carbonate", "lithium hydroxide", "ev battery mineral", "lithium reserve auction"],
        "exclusions": ["lithium drug", "nirvana lithium"],
        "category": "electronics",
    },
}


def match_commodity_candidate(commodity_code: str, headline: str, url: str) -> tuple[bool, float, str]:
    """Evaluate candidate story against explicit commodity rule taxonomy.

    Returns:
        (is_match: bool, confidence: float, match_reason: str)
    """
    rule = COMMODITY_RULES.get(commodity_code)
    if not rule:
        return False, 0.0, f"No rule taxonomy configured for commodity code {commodity_code}"

    text_to_evaluate = f"{headline} {url}".lower()

    # Step 1: Check Exclusions
    for excl in rule.get("exclusions", []):
        if excl.lower() in text_to_evaluate:
            return False, 0.0, f"Rejected by commodity exclusion rule: '{excl}'"

    # Step 2: Check High-Priority Inclusions
    for incl in rule.get("inclusions", []):
        if incl.lower() in text_to_evaluate:
            return True, 0.95, f"Matched explicit inclusion keyword: '{incl}'"

    # Step 3: Check Aliases
    matched_aliases = [alias for alias in rule.get("aliases", []) if alias.lower() in text_to_evaluate]
    if matched_aliases:
        conf = 0.80 if len(matched_aliases) == 1 else 0.90
        return True, conf, f"Matched commodity aliases: {matched_aliases}"

    return False, 0.0, "No qualifying commodity keywords identified."


def update_commodity_news(
    max_rank: int = 5,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Execute staged candidate snapshots and atomic transaction replacement for all tracked commodities."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    run_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)
    logger.info(f"Starting commodity news pipeline [run_id={run_id}]...")
    records_updated = 0

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT commodity_code, name, category FROM tracked_commodities;")
            tracked_rows = cur.fetchall()

            # Query recent candidate GDELT events
            cur.execute("SELECT COALESCE(MAX(event_date), CURRENT_DATE) FROM gdelt_events;")
            ref_date = cur.fetchone()[0] or date.today()
            cutoff_date = ref_date - timedelta(days=30)

            cur.execute(
                """
                SELECT global_event_id, source_url, event_date, num_mentions
                FROM gdelt_events
                WHERE event_date >= %s
                  AND source_url IS NOT NULL AND source_url != ''
                ORDER BY num_mentions DESC, event_date DESC
                LIMIT 150;
                """,
                (cutoff_date,),
            )
            candidate_events = cur.fetchall()

            # Extract page titles once into cache for distinct URLs
            url_title_cache: dict[str, str] = {}

            for code, name, cat in tracked_rows:
                staged_candidates: list[dict[str, Any]] = []
                seen_headlines: set[str] = set()

                rule = COMMODITY_RULES.get(code, {})
                keywords_to_check = [k.lower() for k in rule.get("aliases", []) + rule.get("inclusions", [])]

                for ev_id, raw_url, ev_date, mentions in candidate_events:
                    if len(staged_candidates) >= max_rank:
                        break

                    canonical_url = normalize_url(raw_url)
                    url_lower = canonical_url.lower()

                    # Fast pre-filter: check if URL slug or path contains any commodity keywords
                    has_url_hint = any(kw in url_lower for kw in keywords_to_check)
                    if not has_url_hint and canonical_url not in url_title_cache:
                        # Skip expensive network fetch if URL has no resemblance to this commodity
                        continue

                    if canonical_url not in url_title_cache:
                        extracted_title = headline_extractor.extract_page_title(canonical_url, timeout_seconds=1)
                        url_title_cache[canonical_url] = extracted_title or ""

                    headline = url_title_cache.get(canonical_url, "")
                    if not headline or len(headline.strip()) < 12:
                        continue

                    h_norm = headline.lower().strip()
                    if h_norm in seen_headlines:
                        continue

                    # Evaluate commodity taxonomy match
                    is_match, conf, match_reason = match_commodity_candidate(code, headline, canonical_url)
                    if not is_match or conf < 0.60:
                        continue

                    seen_headlines.add(h_norm)
                    template_brief = generate_template_fallback_brief("commodity_news", headline)

                    # Get or create persistent news_story
                    cur.execute(
                        """
                        INSERT INTO news_stories (canonical_url, content_hash, normalized_title, source_domain, first_seen_at, last_seen_at)
                        VALUES (%s, MD5(%s), %s, SPLIT_PART(%s, '/', 3), NOW(), NOW())
                        ON CONFLICT (canonical_url) DO UPDATE SET last_seen_at = NOW()
                        RETURNING id;
                        """,
                        (canonical_url, headline, headline, canonical_url),
                    )
                    story_id = cur.fetchone()[0]

                    staged_candidates.append({
                        "commodity_code": code,
                        "rank": len(staged_candidates) + 1,
                        "headline": headline,
                        "gdelt_event_id": ev_id,
                        "source_url": canonical_url,
                        "published_at": ev_date,
                        "story_id": story_id,
                        "llm_brief": template_brief,
                        "validation_source": "rules",
                        "brief_source": "template_fallback",
                        "confidence": conf,
                        "relevance_reason": match_reason,
                    })

                # Atomic Publish: Replace snapshot for this commodity in single transaction
                cur.execute("DELETE FROM commodity_news WHERE commodity_code = %s;", (code,))
                for item in staged_candidates:
                    cur.execute(
                        """
                        INSERT INTO commodity_news (
                            commodity_code, rank, headline, gdelt_event_id, source_url,
                            published_at, updated_at, story_id, llm_brief, validation_source,
                            brief_source, confidence, relevance_reason, expires_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            item["commodity_code"],
                            item["rank"],
                            item["headline"],
                            item["gdelt_event_id"],
                            item["source_url"],
                            item["published_at"],
                            item["story_id"],
                            item["llm_brief"],
                            item["validation_source"],
                            item["brief_source"],
                            item["confidence"],
                            item["relevance_reason"],
                            now_utc + timedelta(days=7),
                        ),
                    )
                    records_updated += 1

                if not staged_candidates:
                    logger.info(f"No qualifying commodity news found for {code} ({name}); snapshot expired cleanly.")

        conn.commit()

    logger.info(f"Commodity news pipeline completed: {records_updated} records published.")
    return {"commodity_news_updated": records_updated, "run_id": str(run_id)}
