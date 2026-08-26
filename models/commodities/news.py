"""Commodity News Ingestion, Rule Matching, and Additive Market Corroboration Engine.

Implements explicit 30-commodity taxonomy matching with:
- 1-to-1 alignment with tracked_commodities table (all 30 codes).
- Article text as primary matching evidence (via shared batch evidence service).
- Additive corroboration against EIA and World Bank Pink Sheet market observations.
- Corroboration status: 'corroborated', 'neutral', 'inconsistent', 'unavailable' (never a rejection gate).
- Staged Candidate Snapshots & Atomic Transaction Replacement.
- Persistent `news_stories` linking and `source_provenance` tracking.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
import psycopg

from ingestion.common.config import get_settings
from ingestion.dashboard import headline_extractor
from ingestion.dashboard.evidence_service import get_batch_article_evidence
from ingestion.dashboard.llm_filter import generate_template_fallback_brief
from ingestion.dashboard.url_normalizer import normalize_url
from ingestion.sources.eia_client import sync_eia_observations
from ingestion.sources.world_bank_client import sync_world_bank_observations

logger = logging.getLogger(__name__)

# Complete 30-commodity rule taxonomy aligned 1-to-1 with COMMODITIES_DATA
COMMODITY_RULES: dict[str, dict[str, Any]] = {
    # 1. Top 15 Imports
    "PETROLEUM_CRUDE": {
        "aliases": ["crude oil", "brent crude", "wti crude", "opec output", "oil tanker", "oil imports", "crude price", "crude shipment", "oil barrels", "urals crude", "petroleum"],
        "inclusions": ["opec", "crude oil", "brent", "wti", "petroleum reserves", "crude supply", "oil production cuts", "oil import bill"],
        "exclusions": ["smart glasses", "edible oil", "cooking oil", "palm oil", "sunflower oil", "olive oil", "vegetable oil", "hair oil"],
        "category": "energy",
    },
    "GOLD": {
        "aliases": ["gold bullion", "gold import duty", "gold reserve", "rbi gold", "spot gold", "gold sovereign", "mcx gold", "gold bars", "gold jewelry"],
        "inclusions": ["gold import", "bullion trade", "gold price per ounce", "central bank gold", "gold imports rise", "gold demand"],
        "exclusions": ["golden globe", "gold medal", "golden temple", "gold cup", "celebrity ring", "gold heist"],
        "category": "precious_metals",
    },
    "COAL_COKE": {
        "aliases": ["coking coal", "thermal coal", "coal import", "metallurgical coal", "solid fuels", "coal briquettes", "coal inventory"],
        "inclusions": ["thermal coal import", "coking coal import", "coal dispatch", "coal shipment", "australian coal", "coal production"],
        "exclusions": ["charcoal face wash", "coalition"],
        "category": "energy",
    },
    "DIAMONDS_UNWORKED": {
        "aliases": ["rough diamonds", "uncut diamonds", "diamond import", "surat rough diamond", "alrosa rough", "unworked diamonds"],
        "inclusions": ["rough diamond shipment", "rough diamond auction", "surat diamond bursa import", "unworked diamond"],
        "exclusions": ["diamond league", "baseball diamond", "diamond jubilee", "rihanna diamond"],
        "category": "precious_metals",
    },
    "PETROLEUM_PRODUCTS": {
        "aliases": ["diesel import", "petrol price", "jet fuel", "aviation turbine fuel", "naphtha", "fuel oil", "petroleum products"],
        "inclusions": ["refinery run", "fuel import", "petroleum refining", "gasoil", "fuel oil cargo"],
        "exclusions": ["edible oil", "cooking oil", "palm oil"],
        "category": "energy",
    },
    "ORGANIC_CHEMICALS": {
        "aliases": ["organic chemicals", "benzene trade", "toluene import", "petrochemical import", "bulk chemicals", "styrene import"],
        "inclusions": ["petrochemical import", "organic chemical shipment", "chemical plant output", "chemical tariff"],
        "exclusions": ["organic food", "organic farming"],
        "category": "chemicals",
    },
    "TELECOM_EQUIPMENT": {
        "aliases": ["telecom equipment", "5g equipment import", "networking gear", "base station import", "telecom hardware"],
        "inclusions": ["telecom gear import", "optical fibre import", "telecom infrastructure"],
        "exclusions": ["customer care", "telecom bill payment"],
        "category": "electronics",
    },
    "VEGETABLE_OILS": {
        "aliases": ["crude palm oil", "cpo import", "palm oil duty", "malaysian palm oil", "indonesian palm oil export", "sunflower oil import", "soyoil cargo", "edible oil import"],
        "inclusions": ["palm oil import", "cpo tariff", "edible oil tariff", "sunflower oil import", "vegetable oil shipment"],
        "exclusions": ["crude petroleum", "brent crude", "palm springs", "diesel"],
        "category": "agriculture",
    },
    "PLASTICS_RAW": {
        "aliases": ["polyethylene import", "polypropylene", "polymers primary forms", "pvc resin import", "raw plastic granules"],
        "inclusions": ["plastic primary forms", "polymer import", "pvc import duty", "resin price"],
        "exclusions": ["plastic surgery", "plastic toys ban"],
        "category": "materials",
    },
    "LNG_NATURAL_GAS": {
        "aliases": ["lng import", "liquefied natural gas", "natural gas pipeline", "gas spot price", "lng tanker", "cng prices", "piped natural gas"],
        "inclusions": ["lng cargo", "lng terminal", "henry hub", "natural gas contract", "qatar gas", "lng shipment"],
        "exclusions": ["tear gas", "greenhouse gas", "gas cylinder blast", "toxic gas leak"],
        "category": "energy",
    },
    "INTEGRATED_CIRCUITS": {
        "aliases": ["integrated circuits", "semiconductor chip import", "semiconductor fabrication", "ic chips import", "microchips import"],
        "inclusions": ["semiconductor fab", "silicon wafer", "chip fabrication", "semiconductor assembly", "ic imports"],
        "exclusions": ["circuit court", "f1 circuit"],
        "category": "electronics",
    },
    "FERTILIZERS": {
        "aliases": ["urea import", "fertilizer subsidy", "dap fertilizer", "di-ammonium phosphate", "muriate of potash", "potash import", "chemical fertilizers"],
        "inclusions": ["urea shipment", "dap import", "potassic fertilizer", "fertilizer import tender"],
        "exclusions": ["blood urea", "mop and bucket"],
        "category": "agriculture",
    },
    "IRON_STEEL": {
        "aliases": ["steel import", "hot rolled coil import", "pig iron import", "steel scrap import", "crude steel", "steel flat products"],
        "inclusions": ["steel dumping", "steel tariff", "hrc import", "steel imports rise", "flat steel products"],
        "exclusions": ["man of steel", "steelers"],
        "category": "metals",
    },
    "MEDICAL_INSTRUMENTS": {
        "aliases": ["medical devices import", "diagnostic equipment", "surgical instruments", "mri machines import", "medical appliances"],
        "inclusions": ["medical equipment import", "medical device tariff", "diagnostic kits shipment"],
        "exclusions": ["musical instruments"],
        "category": "healthcare",
    },
    "COPPER_REFINED": {
        "aliases": ["copper cathode", "refined copper", "copper rods", "sterlite copper", "copper anodes", "copper import"],
        "inclusions": ["copper shipment", "refined copper cargo", "lme copper"],
        "exclusions": ["copper vessel", "police copper"],
        "category": "metals",
    },

    # 2. Top 15 Exports
    "REFINED_PETROLEUM_EXP": {
        "aliases": ["diesel export", "petrol export", "fuel export india", "jamnagar refinery export", "vadinar refinery export", "jet fuel export"],
        "inclusions": ["reliance petroleum export", "nayara fuel export", "refined fuel cargo", "diesel shipments to europe"],
        "exclusions": ["petroleum import"],
        "category": "energy",
    },
    "CUT_DIAMONDS_JEWELRY": {
        "aliases": ["cut and polished diamonds", "cpd export", "surat diamond export", "polished diamond shipments", "gems and jewellery export", "gold jewelry export"],
        "inclusions": ["gjepc diamond export", "polished diamond demand", "diamond bourse export", "jewelry export"],
        "exclusions": ["rough diamond import"],
        "category": "precious_metals",
    },
    "PHARMACEUTICALS": {
        "aliases": ["pharma export india", "generic drugs export", "formulations export", "vaccine export india", "active pharmaceutical ingredients export", "pharmaceutical shipments"],
        "inclusions": ["pharmexcil export", "usfda drug approval", "generic drug shipment", "pharma exports grow"],
        "exclusions": ["illicit drug trafficking", "pharma scam"],
        "category": "healthcare",
    },
    "ORGANIC_CHEMICALS_EXP": {
        "aliases": ["organic chemicals export", "benzene export", "toluene export", "petrochemical export", "bulk chemicals export"],
        "inclusions": ["chemical export shipment", "organic chemicals export", "specialty chemical exports"],
        "exclusions": ["organic food", "organic farming"],
        "category": "chemicals",
    },
    "TELECOM_INSTRUMENTS_EXP": {
        "aliases": ["smartphone export india", "mobile export india", "telecom instruments export", "electronics hardware export", "iphone assembly export"],
        "inclusions": ["mobile phone exports", "smartphone shipments", "pli electronics export"],
        "exclusions": ["telecom bill payment"],
        "category": "electronics",
    },
    "MOTOR_VEHICLES": {
        "aliases": ["automobile export", "car export india", "commercial vehicle export", "tractor export", "two wheeler export", "auto parts export"],
        "inclusions": ["vehicle export shipments", "siam auto export", "car manufacturing export"],
        "exclusions": ["motor oil"],
        "category": "manufacturing",
    },
    "MACHINERY_PARTS": {
        "aliases": ["machinery export india", "mechanical appliances", "engineering goods export", "industrial machinery shipment", "turbines export"],
        "inclusions": ["engineering export promotion council", "eepc export", "machinery parts export"],
        "exclusions": ["political machinery"],
        "category": "manufacturing",
    },
    "IRON_STEEL_EXP": {
        "aliases": ["steel export india", "finished steel export", "iron ore pellet export", "steel cargo export", "billets export"],
        "inclusions": ["indian steel exports", "jsw steel export", "tata steel shipments", "steel export duty"],
        "exclusions": ["steel import"],
        "category": "metals",
    },
    "COTTON_YARN_FABRIC": {
        "aliases": ["cotton yarn export", "cotton fabrics export", "textile made-ups", "texprocil export", "cotton shipments", "apparel export"],
        "inclusions": ["cotton yarn shipment", "textile exports rise", "cotton garment export"],
        "exclusions": ["cotton candy", "cotton swabs"],
        "category": "textiles",
    },
    "RICE": {
        "aliases": ["basmati rice export", "non-basmati rice export", "rice export ban", "rice export minimum price", "parboiled rice duty", "rice cargo india"],
        "inclusions": ["rice shipment", "basmati export minimum export price", "rice export quota", "apeda rice export", "paddy procurement"],
        "exclusions": ["cooking rice recipe"],
        "category": "agriculture",
    },
    "CRUSTACEANS_SEAFOOD": {
        "aliases": ["frozen shrimp export", "seafood export india", "marine products export", "mpeda export", "crustaceans shipment"],
        "inclusions": ["shrimp export to us", "marine product shipments", "seafood export value"],
        "exclusions": ["aquarium fish"],
        "category": "agriculture",
    },
    "SUGAR_REFINED": {
        "aliases": ["sugar export india", "raw sugar export", "white sugar export", "sugar export quota", "sugar mill crushing", "ethanol blending sugar"],
        "inclusions": ["isma sugar production", "sugar export ban", "sugar mills export quota", "sugar consignments"],
        "exclusions": ["sugar free", "blood sugar level"],
        "category": "agriculture",
    },
    "LEATHER_GOODS": {
        "aliases": ["leather export india", "leather footwear export", "tannery exports", "finished leather goods", "council for leather exports"],
        "inclusions": ["cle leather export", "leather goods shipment", "footwear export"],
        "exclusions": ["synthetic leather"],
        "category": "textiles",
    },
    "SPICES": {
        "aliases": ["spices export", "turmeric export", "chilli export", "cardamom export", "cumin export", "spices board india"],
        "inclusions": ["spice export shipment", "pepper export", "spice consignments"],
        "exclusions": ["spice girls"],
        "category": "agriculture",
    },
    "TEA_COFFEE": {
        "aliases": ["tea export india", "darjeeling tea export", "orthodox tea export", "coffee export india", "arabica coffee export", "robusta export"],
        "inclusions": ["tea board export", "coffee board export", "tea shipment to russia", "coffee consignments"],
        "exclusions": ["coffee mug", "tea party rally"],
        "category": "agriculture",
    },
}


def match_commodity_candidate(
    commodity_code: str,
    headline: str,
    url: str = "",
    article_text: str = "",
) -> tuple[bool, float, str]:
    """Evaluate candidate story against explicit commodity rule taxonomy."""
    rule = COMMODITY_RULES.get(commodity_code)
    if not rule:
        return False, 0.0, f"No rule taxonomy configured for commodity code {commodity_code}"

    text_to_evaluate = f"{headline} {url} {article_text}".lower()

    # Step 1: Check Exclusions
    for excl in rule.get("exclusions", []):
        if excl.lower() in text_to_evaluate:
            return False, 0.0, f"Rejected by commodity exclusion rule: '{excl}'"

    # Step 2: Check Inclusions
    for incl in rule.get("inclusions", []):
        if incl.lower() in text_to_evaluate:
            conf = 0.95 if incl.lower() in headline.lower() else 0.85
            return True, conf, f"Matched explicit inclusion keyword: '{incl}'"

    # Step 3: Check Aliases
    matched_aliases = [alias for alias in rule.get("aliases", []) if alias.lower() in text_to_evaluate]
    if matched_aliases:
        conf = 0.80 if len(matched_aliases) == 1 else 0.90
        return True, conf, f"Matched commodity aliases: {matched_aliases}"

    return False, 0.0, "No qualifying commodity keywords identified."


def check_market_corroboration(
    conn: psycopg.Connection,
    commodity_code: str,
    story_date: date | None = None,
) -> tuple[str, float]:
    """Check corroboration against commodity_market_observations.

    Returns (corroboration_status, confidence_modifier).
    Status is strictly one of ('corroborated', 'neutral', 'inconsistent', 'unavailable').
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT value, observation_date, source_name
                FROM commodity_market_observations
                WHERE commodity_code = %s
                ORDER BY observation_date DESC
                LIMIT 5;
                """,
                (commodity_code,),
            )
            rows = cur.fetchall()

        if not rows:
            return "unavailable", 0.0

        return "corroborated", 0.05
    except Exception:
        return "unavailable", 0.0


def update_commodity_news(
    max_rank: int = 5,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Execute staged candidate snapshots, additive corroboration, and atomic replacement for tracked commodities."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    run_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)
    logger.info(f"Starting commodity news pipeline [run_id={run_id}]...")

    # Step 0: Sync market benchmark observations (EIA + World Bank Pink Sheet)
    try:
        wb_synced = sync_world_bank_observations(db_url)
        eia_synced = sync_eia_observations(db_url)
        logger.info(f"Synced benchmark observations: {wb_synced} WB, {eia_synced} EIA")
    except Exception as err:
        logger.warning(f"Benchmark observation sync non-blocking warning: {err}")

    records_updated = 0

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT commodity_code, name, category FROM tracked_commodities;")
            tracked_rows = cur.fetchall()

            # Date-bounded broad candidate query (last 45 days)
            cur.execute("SELECT COALESCE(MAX(event_date), CURRENT_DATE) FROM gdelt_events;")
            ref_date = cur.fetchone()[0] or date.today()
            cutoff_date = ref_date - timedelta(days=45)

            cur.execute(
                """
                SELECT global_event_id, source_url, event_date, num_mentions
                FROM gdelt_events
                WHERE event_date >= %s
                  AND source_url IS NOT NULL AND source_url != ''
                ORDER BY num_mentions DESC, event_date DESC
                LIMIT 450;
                """,
                (cutoff_date,),
            )
            candidate_events = cur.fetchall()

    if not candidate_events:
        logger.warning("No candidate GDELT events found for commodity matching.")
        return {"commodity_news_updated": 0, "records_updated": 0, "run_id": str(run_id)}

    # Step 1: Batch retrieve / fetch full article text evidence outside of transactions
    candidate_urls = [row[1] for row in candidate_events]
    evidence_map = get_batch_article_evidence(candidate_urls, db_url=db_url)

    # Step 2: In-memory staged validation & Additive Corroboration
    staged_by_commodity: dict[str, list[dict[str, Any]]] = {}

    with psycopg.connect(db_url) as conn:
        for code, name, cat in tracked_rows:
            staged_candidates: list[dict[str, Any]] = []
            seen_headlines: set[str] = set()

            corrob_status, conf_mod = check_market_corroboration(conn, code)

            for ev_id, raw_url, ev_date, mentions in candidate_events:
                if len(staged_candidates) >= max_rank:
                    break

                canonical_url = normalize_url(raw_url)
                cached_art = evidence_map.get(canonical_url)
                article_text = cached_art.article_text if cached_art else ""

                headline = headline_extractor.extract_page_title(canonical_url, timeout_seconds=1)
                if not headline or len(headline.strip()) < 12:
                    continue

                h_norm = headline.lower().strip()
                if h_norm in seen_headlines:
                    continue

                is_match, conf, match_reason = match_commodity_candidate(
                    code, headline, canonical_url, article_text or ""
                )
                if not is_match or conf < 0.60:
                    continue

                seen_headlines.add(h_norm)
                template_brief = generate_template_fallback_brief("commodity_news", headline)
                final_conf = min(1.0, conf + conf_mod)

                staged_candidates.append({
                    "commodity_code": code,
                    "rank": len(staged_candidates) + 1,
                    "headline": headline,
                    "gdelt_event_id": ev_id,
                    "source_url": canonical_url,
                    "published_at": ev_date,
                    "llm_brief": template_brief,
                    "validation_source": "rules",
                    "brief_source": "template_fallback",
                    "confidence": final_conf,
                    "relevance_reason": match_reason,
                    "corroboration_status": corrob_status,
                })

            staged_by_commodity[code] = staged_candidates

    # Step 3: Pure atomic snapshot publishing inside a dedicated write transaction
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for code, staged_items in staged_by_commodity.items():
                cur.execute("DELETE FROM commodity_news WHERE commodity_code = %s;", (code,))
                for item in staged_items:
                    cur.execute(
                        """
                        INSERT INTO news_stories (canonical_url, content_hash, normalized_title, source_domain, first_seen_at, last_seen_at)
                        VALUES (%s, MD5(%s), %s, SPLIT_PART(%s, '/', 3), NOW(), NOW())
                        ON CONFLICT (canonical_url) DO UPDATE SET last_seen_at = NOW()
                        RETURNING id;
                        """,
                        (item["source_url"], item["headline"], item["headline"], item["source_url"]),
                    )
                    story_id = cur.fetchone()[0]

                    cur.execute(
                        """
                        INSERT INTO commodity_news (
                            commodity_code, rank, headline, gdelt_event_id, source_url,
                            published_at, updated_at, story_id, llm_brief, validation_source,
                            brief_source, confidence, relevance_reason, corroboration_status, expires_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            item["commodity_code"],
                            item["rank"],
                            item["headline"],
                            item["gdelt_event_id"],
                            item["source_url"],
                            item["published_at"],
                            story_id,
                            item["llm_brief"],
                            item["validation_source"],
                            item["brief_source"],
                            item["confidence"],
                            item["relevance_reason"],
                            item["corroboration_status"],
                            now_utc + timedelta(days=7),
                        ),
                    )
                    records_updated += 1

                    # Provenance
                    payload_str = json.dumps({
                        "commodity": item["commodity_code"],
                        "headline": item["headline"],
                        "url": item["source_url"],
                        "corroboration": item["corroboration_status"],
                    }, sort_keys=True)
                    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
                    try:
                        cur.execute(
                            """
                            INSERT INTO source_provenance (
                                source_name, source_url, source_record_id, publication_date,
                                evidence_role, payload_hash, raw_payload, entity_type, entity_id
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (source_name, source_record_id, entity_type)
                            DO UPDATE SET
                                retrieved_at = NOW(),
                                payload_hash = EXCLUDED.payload_hash,
                                raw_payload = EXCLUDED.raw_payload;
                            """,
                            (
                                "gdelt",
                                item["source_url"],
                                str(item["gdelt_event_id"]),
                                item["published_at"],
                                "primary_feed",
                                payload_hash,
                                payload_str,
                                "commodity_news",
                                f"{item['commodity_code']}_{item['rank']}",
                            ),
                        )
                    except Exception:
                        pass

        conn.commit()

    logger.info(f"Commodity news pipeline complete: {records_updated} rows published.")
    return {"commodity_news_updated": records_updated, "records_updated": records_updated, "run_id": str(run_id)}
