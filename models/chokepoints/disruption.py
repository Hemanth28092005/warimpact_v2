"""Maritime Chokepoint Disruption Scoring Engine.

Methodology:
- Primary source: IMF PortWatch disruption alerts and daily transit volume deviation telemetry.
- Geodesic event overlay: Proximate maritime kinetic/conflict events within 250km geodesic radius.
- Status thresholds:
  - green: score < 25.0 (Nominal transit)
  - yellow: 25.0 <= score < 50.0 (Elevated threat)
  - red: score >= 50.0 (Critical disruption)
- Evidence stored in `chokepoint_events` child table.
- Mojibake sanitization on all text fields.
"""

from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Any
import psycopg
from psycopg.types.json import Jsonb

from ingestion.common.config import get_settings
from ingestion.dashboard.evidence_service import get_batch_article_evidence
from ingestion.dashboard.url_normalizer import normalize_url
from ingestion.sources.portwatch_client import (
    PortWatchClient,
    derive_portwatch_status,
    sanitize_text,
    sync_portwatch_chokepoints,
)

logger = logging.getLogger(__name__)

MARITIME_KEYWORDS = [
    "tanker", "vessel", "ship", "cargo", "strait", "sea", "gulf",
    "naval", "navy", "coast guard", "drone attack", "missile", "houthi",
    "red sea", "piracy", "hijack", "blockade", "torpedo", "mines",
    "port", "maritime", "corridor", "anchorage", "bulk carrier", "container ship",
]


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Great-Circle distance between two points in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def is_maritime_relevant(
    event_code: str | None,
    url: str | None,
    quad_class: int | None,
    article_text: str = "",
) -> bool:
    """Filter candidate events for genuine maritime security relevance."""
    combined = f"{url or ''} {article_text}".lower()
    has_maritime_kw = any(kw in combined for kw in MARITIME_KEYWORDS)

    if event_code and (event_code.startswith("18") or event_code.startswith("19")):
        return has_maritime_kw or (quad_class is not None and quad_class == 4)

    return has_maritime_kw


def audit_existing_chokepoint_evidence(conn: psycopg.Connection) -> dict[str, Any]:
    """Audit existing chokepoint_events rows to classify into retained vs quarantined."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ce.id, ce.chokepoint_code, ce.gdelt_event_id, ce.distance_km,
                   ce.contribution_score, ce.reason, g.source_url, g.event_code
            FROM chokepoint_events ce
            LEFT JOIN gdelt_events g ON ce.gdelt_event_id = g.global_event_id
            ORDER BY ce.observed_at DESC
            LIMIT 500;
            """
        )
        rows = cur.fetchall()

    retained = []
    quarantined = []

    for row in rows:
        ce_id, code, ev_id, dist_km, score, reason, url, ecode = row
        url_clean = url or ""
        clean_reason = sanitize_text(reason)
        if any(kw in url_clean.lower() for kw in MARITIME_KEYWORDS) or (dist_km and float(dist_km) <= 150.0) or "PortWatch" in clean_reason:
            retained.append({
                "id": ce_id,
                "chokepoint_code": code,
                "gdelt_event_id": ev_id,
                "distance_km": float(dist_km) if dist_km else 0.0,
                "score": float(score) if score else 0.0,
                "status": "retained",
            })
        else:
            quarantined.append({
                "id": ce_id,
                "chokepoint_code": code,
                "gdelt_event_id": ev_id,
                "distance_km": float(dist_km) if dist_km else 0.0,
                "score": float(score) if score else 0.0,
                "status": "quarantined_non_maritime",
            })

    return {
        "total_audited": len(rows),
        "retained_count": len(retained),
        "quarantined_count": len(quarantined),
    }


def calculate_chokepoint_disruptions(db_url: str | None = None) -> dict[str, int]:
    """Calculate and update disruption scores using PortWatch telemetry and GDELT fallback."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    # Step 1: Execute PortWatch sync
    try:
        sync_portwatch_chokepoints(db_url)
    except Exception as err:
        logger.debug(f"PortWatch sync non-fatal error: {err}")

    # Step 2: Query candidate events for geodesic overlay & fallback
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, name, lat, long, disruption_score, status, validation_source FROM chokepoints;")
            chokepoints = cur.fetchall()

            cur.execute(
                """
                SELECT global_event_id, action_geo_lat, action_geo_long, goldstein_scale,
                       num_mentions, source_url, event_code, quad_class, event_date
                FROM gdelt_events
                WHERE event_date >= CURRENT_DATE - INTERVAL '14 days'
                  AND action_geo_lat IS NOT NULL AND action_geo_long IS NOT NULL
                  AND (quad_class >= 3 OR goldstein_scale <= -4.0 OR event_code LIKE '18%' OR event_code LIKE '19%')
                ORDER BY event_date DESC, num_mentions DESC
                LIMIT 500;
                """
            )
            candidate_events = cur.fetchall()

    candidate_urls = [row[5] for row in candidate_events if row[5]]
    evidence_map = get_batch_article_evidence(candidate_urls, db_url=db_url) if candidate_urls else {}

    updated_count = 0
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Check if validation_source column exists in chokepoints
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'chokepoints' AND column_name = 'validation_source';")
            has_val_col = bool(cur.fetchone())

            for code, name, c_lat, c_long, current_score, current_status, val_src in chokepoints:
                geo_score = 0.0
                related_event_ids: list[int] = []
                geo_reason = None

                for ev_id, e_lat, e_long, goldstein, mentions, url, ecode, quad, ev_date in candidate_events:
                    dist_km = haversine_distance_km(float(c_lat), float(c_long), float(e_lat), float(e_long))
                    if dist_km > 250.0:
                        continue

                    canonical_url = normalize_url(url or "")
                    cached_art = evidence_map.get(canonical_url)
                    art_text = cached_art.article_text if cached_art else ""

                    if not is_maritime_relevant(ecode, canonical_url, quad, art_text or ""):
                        continue

                    severity = abs(float(goldstein or -5.0)) * 2.0
                    mention_factor = min(4.0, float(mentions or 1) / 25.0)
                    proximity_decay = math.exp(-dist_km / 80.0)

                    event_impact = round((severity / 10.0) * mention_factor * proximity_decay * 10.0, 2)
                    geo_score += event_impact
                    related_event_ids.append(ev_id)

                    reason_str = sanitize_text(f"Maritime event {ev_id} within {dist_km:.1f}km of {name} (impact +{event_impact:.1f})")
                    if event_impact >= 3.0:
                        geo_reason = reason_str

                    cur.execute(
                        """
                        INSERT INTO chokepoint_events (
                            chokepoint_code, gdelt_event_id, distance_km, contribution_score,
                            reason, observed_at, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (chokepoint_code, gdelt_event_id, observed_at) DO NOTHING;
                        """,
                        (code, ev_id, dist_km, event_impact, reason_str, ev_date),
                    )

                # Combine PortWatch telemetry score with kinetic geodesic score
                base_pw_score = float(current_score or 0.0)
                final_score = min(100.0, max(base_pw_score, round(geo_score, 2)))
                status = "red" if final_score >= 50.0 else ("yellow" if final_score >= 25.0 else "green")
                final_reason = geo_reason if (geo_reason and geo_score > base_pw_score) else sanitize_text(f"Nominal maritime transit at {name}")
                effective_val_source = "gdelt" if (geo_score > base_pw_score and geo_score >= 25.0) else (val_src or "portwatch")

                if has_val_col:
                    cur.execute(
                        """
                        UPDATE chokepoints
                        SET disruption_score = %s,
                            status = %s,
                            related_event_ids = %s,
                            last_disruption_reason = COALESCE(%s, last_disruption_reason),
                            validation_source = %s,
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE code = %s;
                        """,
                        (final_score, status, Jsonb(related_event_ids[:10]), final_reason, effective_val_source, code),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE chokepoints
                        SET disruption_score = %s,
                            status = %s,
                            related_event_ids = %s,
                            last_disruption_reason = COALESCE(%s, last_disruption_reason),
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE code = %s;
                        """,
                        (final_score, status, Jsonb(related_event_ids[:10]), final_reason, code),
                    )
                updated_count += 1

        conn.commit()

    logger.info(f"Chokepoint disruption engine completed: {updated_count} chokepoints updated.")
    return {"chokepoints_updated": updated_count}
