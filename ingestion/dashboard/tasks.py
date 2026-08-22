"""Shared Parameterized Celery Ingestion Tasks for Phase 6a Dashboard Data Layer.

Implements single parameterized ingestion pattern for:
- regional_headlines (staged snapshot on (region, rank))
- government_actions (strict Indian actor validation, canonical action types, rank 1..10)
- protests (granular geography location_name/level/city/state, multi-factor normalized severity 0..100)

Guarantees:
- Title extraction with leakage stripping and mojibake correction.
- Anti-hallucination brief grounding and deterministic template fallback.
- Persistent news_stories deduplication.
- Canonical controlled vocabularies and constraints.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg
from celery import shared_task  # type: ignore[import-untyped]

from ingestion.common.config import get_settings
from ingestion.dashboard import headline_extractor
from ingestion.dashboard.llm_filter import (
    resolve_event_location,
    validate_headline_relevance,
    generate_template_fallback_brief,
)
from ingestion.dashboard.url_normalizer import get_or_create_news_story, normalize_url

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
) -> float:
    """Calculate multi-factor non-degenerate protest severity score [10.0, 100.0].

    Components:
    - Base subtype weight: 30 (demonstration) to 45 (mass strike / agitation)
    - Escalation / violence bonus: +25 for clashes/tear-gas/detentions, +10 for sit-in/road blockade
    - Mention volume: up to +20 points
    - Tone penalty: up to +10 points for sharply negative tone (< -5.0)
    - Recency bonus: +10 points if within 7 days, +5 if within 14 days
    """
    score = 30.0

    # 1. Subtype weight
    if event_code in {"145", "1451", "1452"}:  # Strike or boycott
        score = 42.0
    elif event_code in {"141", "1411", "1412"}:  # Demonstration or rally
        score = 35.0

    # 2. Violence / Escalation indicators
    h_lower = headline.lower()
    clash_kws = ["clash", "tear gas", "lathi", "detain", "arrest", "stone pelting", "water cannon", "crackdown", "fir against"]
    sit_in_kws = ["dharna", "sit-in", "rail roko", "rasta roko", "highway block", "hunger strike", "shambhu border"]

    if any(k in h_lower for k in clash_kws):
        score += 25.0
    elif any(k in h_lower for k in sit_in_kws):
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
    """Single parameterized task runner for dashboard feeds with staged atomic publish."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    logger.info(f"Starting dashboard feed ingestion: feed_type={feed_type}, key={upsert_key}")
    records_updated = 0
    rejections_count = 0

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(event_date), CURRENT_DATE) FROM gdelt_events;")
            ref_date = cur.fetchone()[0] or date.today()

            if feed_type == "regional_headlines":
                region = filter_params["region"]
                countries = filter_params["countries"]
                cutoff_date = ref_date - timedelta(days=14)

                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, num_mentions, avg_tone,
                           COALESCE(actor1_country_code, action_geo_country_code) AS country_code,
                           event_code
                    FROM gdelt_events
                    WHERE (action_geo_country_code = ANY(%s) OR actor1_country_code = ANY(%s))
                      AND source_url IS NOT NULL AND source_url != ''
                      AND event_date >= %s
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 60;
                    """,
                    (countries, countries, cutoff_date),
                )
                candidates = cur.fetchall()
                staged: list[dict[str, Any]] = []
                seen_headlines: set[str] = set()

                for ev_id, raw_url, ev_date, mentions, tone, ccode, ecode in candidates:
                    if len(staged) >= max_rank:
                        break

                    canonical_url = normalize_url(raw_url)
                    headline = headline_extractor.extract_page_title(canonical_url, timeout_seconds=2)
                    if not headline or len(headline.strip()) < 12:
                        continue

                    h_norm = headline.lower().strip()
                    if h_norm in seen_headlines:
                        continue

                    is_rel, conf, reason, brief, val_src, brief_src, actor, act_type = validate_headline_relevance(
                        "regional_headlines", headline, canonical_url, ecode or ""
                    )
                    if not is_rel:
                        rejections_count += 1
                        continue

                    seen_headlines.add(h_norm)

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

                    staged.append({
                        "region": region,
                        "rank": len(staged) + 1,
                        "headline": headline,
                        "gdelt_event_id": ev_id,
                        "source_url": canonical_url,
                        "published_at": ev_date,
                        "story_id": story_id,
                        "llm_brief": brief,
                        "validation_source": val_src,
                        "brief_source": brief_src,
                        "confidence": conf,
                        "relevance_reason": reason,
                    })

                # Atomic replacement of regional headline ranks
                cur.execute("DELETE FROM regional_headlines WHERE region = %s;", (region,))
                for item in staged:
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
                            item["source_url"], item["published_at"], item["story_id"],
                            item["llm_brief"], item["validation_source"], item["brief_source"],
                            item["confidence"], item["relevance_reason"],
                        ),
                    )
                    records_updated += 1

            elif feed_type == "government_actions":
                cutoff_date = ref_date - timedelta(days=21)

                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, event_code, num_mentions
                    FROM gdelt_events
                    WHERE (action_geo_country_code = 'IN' OR actor1_country_code = 'IND' OR action_geo_country_code = 'IND')
                      AND (event_code LIKE '01%%' OR event_code LIKE '02%%' OR event_code LIKE '03%%' OR event_code LIKE '08%%')
                      AND source_url IS NOT NULL AND source_url != ''
                      AND event_date >= %s
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 60;
                    """,
                    (cutoff_date,),
                )
                candidates = cur.fetchall()
                staged = []
                seen_headlines = set()

                for ev_id, raw_url, ev_date, ecode, mentions in candidates:
                    if len(staged) >= max_rank:
                        break

                    canonical_url = normalize_url(raw_url)
                    headline = headline_extractor.extract_page_title(canonical_url, timeout_seconds=2)
                    if not headline or len(headline.strip()) < 12:
                        continue

                    h_norm = headline.lower().strip()
                    if h_norm in seen_headlines:
                        continue

                    is_rel, conf, reason, brief, val_src, brief_src, actor, act_type = validate_headline_relevance(
                        "government_actions", headline, canonical_url, ecode or ""
                    )
                    if not is_rel:
                        rejections_count += 1
                        continue

                    seen_headlines.add(h_norm)

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

                    staged.append({
                        "rank": len(staged) + 1,
                        "headline": headline,
                        "action_type": act_type if act_type in {'diplomatic', 'regulatory', 'legislative', 'judicial', 'administrative', 'fiscal', 'security'} else 'administrative',
                        "gdelt_event_id": ev_id,
                        "source_url": canonical_url,
                        "published_at": ev_date,
                        "story_id": story_id,
                        "llm_brief": brief,
                        "validation_source": val_src,
                        "brief_source": brief_src,
                        "confidence": conf,
                        "relevance_reason": reason,
                        "actor_entity": actor or "Government of India",
                    })

                # Atomic replacement of top 10 government actions
                cur.execute("DELETE FROM government_actions;")
                for item in staged:
                    cur.execute(
                        """
                        INSERT INTO government_actions (
                            rank, headline, action_type, gdelt_event_id, source_url, published_at,
                            story_id, llm_brief, validation_source, brief_source, confidence,
                            relevance_reason, actor_entity, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
                        """,
                        (
                            item["rank"], item["headline"], item["action_type"], item["gdelt_event_id"],
                            item["source_url"], item["published_at"], item["story_id"],
                            item["llm_brief"], item["validation_source"], item["brief_source"],
                            item["confidence"], item["relevance_reason"], item["actor_entity"],
                        ),
                    )
                    records_updated += 1

            elif feed_type == "protests":
                cutoff_date = ref_date - timedelta(days=45)
                cleanup_date = ref_date - timedelta(days=60)

                cur.execute("DELETE FROM protests WHERE event_date < %s;", (cleanup_date,))

                cur.execute(
                    """
                    SELECT global_event_id, source_url, event_date, action_geo_lat, action_geo_long, num_mentions, goldstein_scale, avg_tone, event_code
                    FROM gdelt_events
                    WHERE (action_geo_country_code = 'IND' OR action_geo_country_code = 'IN')
                      AND event_code LIKE '14%%'
                      AND event_code NOT LIKE '18%%' AND event_code NOT LIKE '19%%'
                      AND source_url IS NOT NULL AND source_url != ''
                      AND event_date >= %s
                    ORDER BY num_mentions DESC, event_date DESC
                    LIMIT 60;
                    """,
                    (cutoff_date,),
                )
                candidates = cur.fetchall()

                for ev_id, raw_url, ev_date, lat, long_, mentions, goldstein, tone, ecode in candidates:
                    canonical_url = normalize_url(raw_url)
                    headline = headline_extractor.extract_page_title(canonical_url, timeout_seconds=2)
                    if not headline or len(headline.strip()) < 12:
                        continue

                    is_rel, conf, reason, brief, val_src, brief_src, _, _ = validate_headline_relevance(
                        "protests", headline, canonical_url, ecode or ""
                    )
                    if not is_rel:
                        rejections_count += 1
                        continue

                    # Granular location hierarchy resolution
                    loc_name, loc_level, city, state, country_code = resolve_event_location(
                        lat=float(lat) if lat is not None else None,
                        long_=float(long_) if long_ is not None else None,
                        url=canonical_url,
                        headline=headline,
                    )

                    # Multi-factor normalized severity
                    severity = calculate_protest_severity(
                        event_code=ecode or "140",
                        headline=headline,
                        num_mentions=mentions,
                        avg_tone=float(tone) if tone is not None else 0.0,
                        event_date=ev_date,
                        ref_date=ref_date,
                    )

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

                    # Deterministic deduplication key for protests
                    dedup_key = city or loc_name or "India"

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
                            dedup_key, loc_name, loc_level, state, country_code,
                            ev_date, headline, lat, long_, ev_id, canonical_url,
                            severity, story_id, brief, val_src, brief_src, conf,
                        ),
                    )
                    records_updated += 1

        conn.commit()

    logger.info(f"Feed {feed_type} complete: {records_updated} updated, {rejections_count} rejected.")
    return {"feed_type": feed_type, "records_updated": records_updated, "rejections_count": rejections_count}


@shared_task(name="ingestion.dashboard.tasks.run_regional_headlines")
def run_regional_headlines(db_url: str | None = None) -> dict[str, int]:
    """15-min scheduled task for regional_headlines across 7 regions."""
    total_updated = 0
    total_rejected = 0
    for region, countries in REGION_MAPPING.items():
        res = ingest_gdelt_dashboard_feed(
            feed_type="regional_headlines",
            filter_params={"region": region, "countries": countries},
            upsert_key="region_rank",
            max_rank=10,
            db_url=db_url,
        )
        total_updated += res["records_updated"]
        total_rejected += res.get("rejections_count", 0)
    return {"total_regional_headlines_updated": total_updated, "total_rejected": total_rejected}


@shared_task(name="ingestion.dashboard.tasks.run_government_actions")
def run_government_actions(db_url: str | None = None) -> dict[str, int]:
    """15-min scheduled task for India government_actions (top 10 by rank)."""
    res = ingest_gdelt_dashboard_feed(
        feed_type="government_actions",
        filter_params={},
        upsert_key="rank",
        max_rank=10,
        db_url=db_url,
    )
    return {"government_actions_updated": res["records_updated"], "rejections_count": res.get("rejections_count", 0)}


@shared_task(name="ingestion.dashboard.tasks.run_protests")
def run_protests(db_url: str | None = None) -> dict[str, int]:
    """10-min scheduled task for India protests."""
    res = ingest_gdelt_dashboard_feed(
        feed_type="protests",
        filter_params={"country_code": "IND"},
        upsert_key="city_date_headline",
        db_url=db_url,
    )
    return {"protests_updated": res["records_updated"], "rejections_count": res.get("rejections_count", 0)}
