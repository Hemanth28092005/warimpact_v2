"""Shared Parameterized Celery Ingestion Tasks for Phase 6a Dashboard Data Layer.

Implements single parameterized ingestion pattern with:
- Source swap for Protests (ACLED with graceful feature-flagged fallback to GDELT).
- Source swap for Chokepoints (IMF PortWatch with geodesic GDELT fallback).
- Additive PIB & data.gov.in corroboration for Government Actions.
- Asynchronous batch evidence retrieval via evidence_service (zero in-transaction HTTP requests).
- Full article-text grounding and anti-hallucination verification.
- Staged candidate snapshots and atomic transaction replacement.
- Granular protest geography (venue/city/state/national) and multi-factor normalized severity (0..100).
- Strict Indian government action actor and action-type classification.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg
from celery import shared_task  # type: ignore[import-untyped]

from ingestion.common.config import get_settings
from ingestion.dashboard import headline_extractor
from ingestion.dashboard.entities import is_cjp_entity, validate_cjp_claim
from ingestion.dashboard.evidence_service import get_batch_article_evidence
from ingestion.dashboard.llm_filter import (
    resolve_event_location,
    validate_headline_relevance,
    generate_template_fallback_brief,
)
from ingestion.dashboard.url_normalizer import normalize_url
from ingestion.sources.acled_client import (
    ACLEDClient,
    map_acled_record_to_protest,
    record_acled_provenance,
)
from ingestion.sources.datagovin_client import sync_datagovin_provenance
from ingestion.sources.pib_client import PIBClient, classify_pib_action_type, sync_pib_government_actions
from ingestion.sources.portwatch_client import sync_portwatch_chokepoints

logger = logging.getLogger(__name__)

REGION_MAPPING = {
    "united_states": ["USA"],
    "india": ["IND"],
    "africa": ["SDN", "ETH", "SOM", "NGA", "ZAF"],
    "asia_pacific": ["CHN", "JPN", "KOR", "TWN", "IDN", "MYS", "PHL", "VNM", "MMR"],
    "middle_east": ["ISR", "IRN", "SAU", "TUR", "SYR", "IRQ", "YEM", "EGY"],
    "europe": ["RUS", "UKR", "DEU", "FRA", "GBR", "POL", "BLR"],
    "latin_america_australia": ["BRA", "MEX", "COL", "VEN", "AUS"],
}


def calculate_protest_severity(
    event_code: str,
    headline: str,
    num_mentions: int | None,
    avg_tone: float | None,
    event_date: date,
    ref_date: date,
    article_text: str = "",
) -> float:
    """Calculate multi-factor non-degenerate protest severity score [10.0, 100.0]."""
    score = 30.0

    # 1. Subtype weight
    if event_code in {"145", "1451", "1452"}:  # Strike or boycott
        score = 42.0
    elif event_code in {"141", "1411", "1412"}:  # Demonstration or rally
        score = 35.0

    # 2. Violence / Escalation indicators in headline or article text
    combined = f"{headline} {article_text}".lower()
    clash_kws = ["clash", "tear gas", "lathi", "detain", "arrest", "stone pelting", "water cannon", "crackdown", "fir against"]
    sit_in_kws = ["dharna", "sit-in", "rail roko", "rasta roko", "highway block", "hunger strike", "shambhu border"]

    if any(k in combined for k in clash_kws):
        score += 25.0
    elif any(k in combined for k in sit_in_kws):
        score += 12.0

    # 3. Mention volume factor (0 to 20)
    mentions = num_mentions or 1
    score += min(20.0, float(mentions) * 1.5)

    # 4. Tone penalty (0 to 10)
    tone = float(avg_tone or 0.0)
    if tone < -5.0:
        score += 10.0
    elif tone < -2.0:
        score += 5.0

    # 5. Recency factor (0 to 10)
    days_old = max(0, (ref_date - event_date).days)
    if days_old <= 7:
        score += 10.0
    elif days_old <= 14:
        score += 5.0

    return min(100.0, max(10.0, round(score, 2)))


def ingest_gdelt_dashboard_feed(
    feed_type: str,
    filter_params: dict[str, Any],
    upsert_key: str,
    max_rank: int = 10,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Execute single-parameterized ingestion pipeline with full article text validation."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    logger.info(f"Starting {feed_type} feed ingestion with params: {filter_params}...")

    # Step 1: Candidate Selection (read-only query)
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(event_date), CURRENT_DATE) FROM gdelt_events;")
            ref_date = cur.fetchone()[0] or date.today()
            cutoff_date = ref_date - timedelta(days=filter_params.get("lookback_days", 30))

            if feed_type == "regional_headlines":
                countries = filter_params["countries"]
                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, num_mentions, avg_tone, event_code
                    FROM gdelt_events
                    WHERE event_date >= %s
                      AND action_geo_country_code = ANY(%s)
                      AND source_url IS NOT NULL AND source_url != ''
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 250;
                    """,
                    (cutoff_date, countries),
                )
                candidates = cur.fetchall()

            elif feed_type == "government_actions":
                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, num_mentions, avg_tone, event_code
                    FROM gdelt_events
                    WHERE event_date >= %s
                      AND action_geo_country_code = 'IND'
                      AND (
                          actor1_type IN ('GOV', 'MIL', 'COP', 'JUD')
                          OR actor2_type IN ('GOV', 'MIL', 'COP', 'JUD')
                          OR event_code LIKE '02%%' OR event_code LIKE '03%%' OR event_code LIKE '04%%' OR event_code LIKE '05%%'
                          OR event_code LIKE '08%%' OR event_code LIKE '09%%' OR event_code LIKE '10%%'
                      )
                      AND source_url IS NOT NULL AND source_url != ''
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 300;
                    """,
                    (cutoff_date,),
                )
                candidates = cur.fetchall()

            elif feed_type == "protests":
                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, action_geo_lat,
                           action_geo_long, num_mentions, goldstein_scale, avg_tone, event_code
                    FROM gdelt_events
                    WHERE event_date >= %s
                      AND action_geo_country_code = 'IND'
                      AND (event_code LIKE '14%%' OR event_code = '140')
                      AND source_url IS NOT NULL AND source_url != ''
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 250;
                    """,
                    (cutoff_date,),
                )
                candidates = cur.fetchall()

            else:
                raise ValueError(f"Unsupported feed_type: {feed_type}")

    if not candidates:
        logger.warning(f"No candidate events found for feed {feed_type}.")
        return {"feed_type": feed_type, "records_updated": 0, "rejections_count": 0}

    # Step 2: Batch Evidence Retrieval (Zero in-transaction HTTP)
    candidate_urls = [row[1] for row in candidates]
    evidence_map = get_batch_article_evidence(candidate_urls, db_url=db_url)

    # Step 3: In-Memory Staged Validation
    staged_items: list[dict[str, Any]] = []
    seen_headlines: set[str] = set()
    rejections_count = 0
    records_updated = 0

    if feed_type == "regional_headlines":
        region = filter_params["region"]
        for ev_id, raw_url, ev_date, mentions, tone, ecode in candidates:
            if len(staged_items) >= max_rank:
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

            is_rel, conf, reason, brief, val_src, brief_src, _, _ = validate_headline_relevance(
                "regional_headlines", headline, canonical_url, ecode or "", article_text or ""
            )
            if not is_rel:
                rejections_count += 1
                continue

            seen_headlines.add(h_norm)
            staged_items.append({
                "region": region,
                "rank": len(staged_items) + 1,
                "headline": headline,
                "gdelt_event_id": ev_id,
                "source_url": canonical_url,
                "published_at": ev_date,
                "llm_brief": brief,
                "validation_source": val_src if val_src in {"groq", "gemini", "rules", "legacy_import"} else "rules",
                "brief_source": brief_src,
                "confidence": conf,
                "relevance_reason": reason,
            })

    elif feed_type == "government_actions":
        for ev_id, raw_url, ev_date, mentions, tone, ecode in candidates:
            if len(staged_items) >= max_rank:
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

            is_rel, conf, reason, brief, val_src, brief_src, actor, act_type = validate_headline_relevance(
                "government_actions", headline, canonical_url, ecode or "", article_text or ""
            )
            if not is_rel:
                rejections_count += 1
                continue

            # Classify action type into canonical vocabulary
            classified_type, classified_actor = classify_pib_action_type(f"{headline} {article_text}")
            canonical_action_type = classified_type if classified_type in {
                "diplomatic", "regulatory", "legislative", "judicial", "administrative", "fiscal", "security"
            } else "administrative"

            seen_headlines.add(h_norm)
            staged_items.append({
                "rank": len(staged_items) + 1,
                "headline": headline,
                "action_type": canonical_action_type,
                "gdelt_event_id": ev_id,
                "source_url": canonical_url,
                "published_at": ev_date,
                "llm_brief": brief,
                "validation_source": val_src if val_src in {"groq", "gemini", "rules", "legacy_import"} else "rules",
                "brief_source": brief_src,
                "confidence": conf,
                "relevance_reason": reason,
                "actor_entity": actor or classified_actor,
                "corroboration_status": "neutral",
            })

    elif feed_type == "protests":
        for ev_id, raw_url, ev_date, lat, long_, mentions, goldstein, tone, ecode in candidates:
            canonical_url = normalize_url(raw_url)
            cached_art = evidence_map.get(canonical_url)
            article_text = cached_art.article_text if cached_art else ""

            headline = headline_extractor.extract_page_title(canonical_url, timeout_seconds=1)
            if not headline or len(headline.strip()) < 12:
                continue

            if is_cjp_entity(f"{headline} {article_text}"):
                cjp_valid, cjp_reason, cjp_conf = validate_cjp_claim(headline, article_text or "")
                if not cjp_valid:
                    rejections_count += 1
                    continue
                is_rel = True
                conf = cjp_conf
                reason = cjp_reason
                val_src = "rules"
                brief_src = "template_fallback"
                brief = generate_template_fallback_brief("protests", headline)
            else:
                is_rel, conf, reason, brief, val_src, brief_src, _, _ = validate_headline_relevance(
                    "protests", headline, canonical_url, ecode or "", article_text or ""
                )
                if not is_rel:
                    rejections_count += 1
                    continue

            # Resolve location hierarchy
            loc_name, loc_level, city, state, country_code = resolve_event_location(
                headline=headline,
                article_text=article_text or "",
                lat=float(lat) if lat is not None else None,
                long_=float(long_) if long_ is not None else None,
            )

            # Multi-factor normalized severity
            severity = calculate_protest_severity(
                event_code=ecode or "140",
                headline=headline,
                num_mentions=mentions,
                avg_tone=float(tone) if tone is not None else 0.0,
                event_date=ev_date,
                ref_date=ref_date,
                article_text=article_text or "",
            )

            dedup_key = city or loc_name or "India"
            staged_items.append({
                "city": dedup_key,
                "location_name": loc_name,
                "location_level": loc_level,
                "state": state,
                "country_code": country_code,
                "event_date": ev_date,
                "headline": headline,
                "lat": lat,
                "long": long_,
                "gdelt_event_id": ev_id,
                "source_url": canonical_url,
                "severity": severity,
                "llm_brief": brief,
                "validation_source": val_src if val_src in {"groq", "gemini", "rules", "legacy_import"} else "rules",
                "brief_source": brief_src,
                "confidence": conf,
            })

    # Step 4: Atomic snapshot publishing inside a dedicated write transaction
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            if feed_type == "regional_headlines":
                region = filter_params["region"]
                cur.execute("DELETE FROM regional_headlines WHERE region = %s;", (region,))
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
                        INSERT INTO regional_headlines (
                            region, rank, headline, gdelt_event_id, source_url, published_at,
                            story_id, llm_brief, validation_source, brief_source, confidence,
                            relevance_reason, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
                        """,
                        (
                            item["region"], item["rank"], item["headline"], item["gdelt_event_id"],
                            item["source_url"], item["published_at"], story_id,
                            item["llm_brief"], item["validation_source"], item["brief_source"],
                            item["confidence"], item["relevance_reason"],
                        ),
                    )
                    records_updated += 1

            elif feed_type == "government_actions":
                cur.execute("DELETE FROM government_actions;")
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
                        INSERT INTO government_actions (
                            rank, headline, action_type, gdelt_event_id, source_url, published_at,
                            story_id, llm_brief, validation_source, brief_source, confidence,
                            relevance_reason, actor_entity, corroboration_status, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
                        """,
                        (
                            item["rank"], item["headline"], item["action_type"], item["gdelt_event_id"],
                            item["source_url"], item["published_at"], story_id,
                            item["llm_brief"], item["validation_source"], item["brief_source"],
                            item["confidence"], item["relevance_reason"], item["actor_entity"],
                            item.get("corroboration_status", "unavailable"),
                        ),
                    )
                    records_updated += 1

            elif feed_type == "protests":
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
                        INSERT INTO protests (
                            city, location_name, location_level, state, country_code,
                            event_date, headline, action_geo_lat, action_geo_long,
                            gdelt_event_id, source_url, event_severity, story_id,
                            llm_brief, validation_source, brief_source, confidence, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (city, event_date, headline) DO UPDATE
                        SET location_name = EXCLUDED.location_name,
                            location_level = EXCLUDED.location_level,
                            state = EXCLUDED.state,
                            country_code = EXCLUDED.country_code,
                            action_geo_lat = EXCLUDED.action_geo_lat,
                            action_geo_long = EXCLUDED.action_geo_long,
                            gdelt_event_id = EXCLUDED.gdelt_event_id,
                            source_url = EXCLUDED.source_url,
                            event_severity = EXCLUDED.event_severity,
                            story_id = EXCLUDED.story_id,
                            llm_brief = EXCLUDED.llm_brief,
                            validation_source = EXCLUDED.validation_source,
                            brief_source = EXCLUDED.brief_source,
                            confidence = EXCLUDED.confidence,
                            updated_at = NOW();
                        """,
                        (
                            item["city"], item["location_name"], item["location_level"], item["state"], item["country_code"],
                            item["event_date"], item["headline"], item["lat"], item["long"], item["gdelt_event_id"], item["source_url"],
                            item["severity"], story_id, item["llm_brief"], item["validation_source"], item["brief_source"], item["confidence"],
                        ),
                    )
                    records_updated += 1

        conn.commit()

    logger.info(f"Feed {feed_type} complete: {records_updated} updated, {rejections_count} rejected.")
    return {"feed_type": feed_type, "records_updated": records_updated, "rejections_count": rejections_count}


@shared_task(name="ingestion.dashboard.tasks.run_regional_headlines")
def run_regional_headlines(region: str = "middle_east", db_url: str | None = None) -> dict[str, Any]:
    """Execute regional headlines ingestion for a specified region."""
    countries = REGION_MAPPING.get(region, ["USA"])
    res = ingest_gdelt_dashboard_feed(
        feed_type="regional_headlines",
        filter_params={"region": region, "countries": countries, "lookback_days": 30},
        upsert_key="region",
        max_rank=10,
        db_url=db_url,
    )
    res["regional_headlines_updated"] = res.get("records_updated", 0)
    return res


@shared_task(name="ingestion.dashboard.tasks.run_government_actions")
def run_government_actions(max_rank: int = 10, db_url: str | None = None) -> dict[str, Any]:
    """Execute official government actions ingestion with PIB & data.gov.in corroboration."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    # Step 1: Sync corroborating evidence from PIB and data.gov.in
    try:
        pib_count = sync_pib_government_actions(db_url)
        dgov_count = sync_datagovin_provenance(db_url)
        logger.info(f"Synced {pib_count} PIB releases and {dgov_count} data.gov.in records.")
    except Exception as err:
        logger.warning(f"Corroborating source fetch non-blocking warning: {err}")

    # Step 2: Run core parameterized GDELT government actions ingestion
    res = ingest_gdelt_dashboard_feed(
        feed_type="government_actions",
        filter_params={"lookback_days": 30},
        upsert_key="rank",
        max_rank=max_rank,
        db_url=db_url,
    )
    res["government_actions_updated"] = res.get("records_updated", 0)
    return res


@shared_task(name="ingestion.dashboard.tasks.run_protests")
def run_protests(limit: int = 100, db_url: str | None = None) -> dict[str, Any]:
    """Execute protests ingestion via ACLED with graceful fallback to GDELT."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    acled_client = ACLEDClient()
    if acled_client.is_configured:
        logger.info("Executing ACLED protest ingestion pipeline...")
        raw_events = acled_client.fetch_protest_events(country="India", limit=limit)
        if raw_events:
            records_updated = 0
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    for raw in raw_events:
                        mapped = map_acled_record_to_protest(raw)
                        cur.execute(
                            """
                            INSERT INTO protests (
                                city, location_name, location_level, state, country_code,
                                event_date, headline, action_geo_lat, action_geo_long,
                                event_severity, llm_brief, validation_source, brief_source,
                                confidence, source_url, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (city, event_date, headline) DO UPDATE
                            SET location_name = EXCLUDED.location_name,
                                location_level = EXCLUDED.location_level,
                                state = EXCLUDED.state,
                                country_code = EXCLUDED.country_code,
                                action_geo_lat = EXCLUDED.action_geo_lat,
                                action_geo_long = EXCLUDED.action_geo_long,
                                event_severity = EXCLUDED.event_severity,
                                llm_brief = EXCLUDED.llm_brief,
                                validation_source = 'acled',
                                brief_source = EXCLUDED.brief_source,
                                confidence = EXCLUDED.confidence,
                                source_url = EXCLUDED.source_url,
                                updated_at = NOW()
                            RETURNING id;
                            """,
                            (
                                mapped["city"] or mapped["location_name"],
                                mapped["location_name"],
                                mapped["location_level"],
                                mapped["state"],
                                mapped["country_code"],
                                mapped["event_date"],
                                mapped["headline"],
                                mapped["action_geo_lat"],
                                mapped["action_geo_long"],
                                mapped["event_severity"],
                                mapped["llm_brief"],
                                mapped["validation_source"],
                                mapped["brief_source"],
                                mapped["confidence"],
                                mapped["source_url"],
                            ),
                        )
                        protest_id = cur.fetchone()[0]
                        record_acled_provenance(conn, protest_id, mapped)
                        records_updated += 1
                conn.commit()

            logger.info(f"ACLED protest pipeline updated {records_updated} records.")
            return {
                "feed_type": "protests",
                "source": "acled",
                "records_updated": records_updated,
                "protests_updated": records_updated,
            }

    logger.info("ACLED not configured or empty; falling back to GDELT protest pipeline.")
    res = ingest_gdelt_dashboard_feed(
        feed_type="protests",
        filter_params={"lookback_days": 30},
        upsert_key="city",
        max_rank=limit,
        db_url=db_url,
    )
    res["source"] = "gdelt_fallback"
    res["protests_updated"] = res.get("records_updated", 0)
    return res


@shared_task(name="ingestion.dashboard.tasks.run_chokepoints")
def run_chokepoints(db_url: str | None = None) -> dict[str, Any]:
    """Execute chokepoints ingestion via IMF PortWatch with geodesic GDELT fallback."""
    if not db_url:
        db_url = get_settings().psycopg_database_url
    return sync_portwatch_chokepoints(db_url)
