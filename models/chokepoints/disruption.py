"""Maritime Chokepoint Disruption Scoring Engine.

Formula & Methodology:
- Disruption Score [0.0, 100.0] calculated from proximate maritime kinetic/conflict events within a 250km geodesic radius.
- Decay Formula:
  impact = min(25.0, (severity_weight * mention_weight * math.exp(-distance_km / 80.0)))
- Exact Canonical Status Thresholds:
  - green: score < 25.0 (Nominal transit)
  - yellow: 25.0 <= score < 50.0 (Elevated threat)
  - red: score >= 50.0 (Critical disruption)
- Evidence is relationally stored into the `chokepoint_events` table with uniqueness on (chokepoint_code, gdelt_event_id, observed_at).
"""

from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Any
import psycopg
from psycopg.types.json import Jsonb

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

# Maritime threat keywords for filtering out landlocked non-maritime events
MARITIME_KEYWORDS = [
    "tanker", "vessel", "ship", "cargo", "strait", "sea", "gulf",
    "naval", "navy", "coast guard", "drone attack", "missile", "houthi",
    "red sea", "piracy", "hijack", "blockade", "torpedo", "mines",
    "port", "maritime", "corridor", "anchorage",
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


def is_maritime_relevant(event_code: str | None, url: str | None, quad_class: int | None) -> bool:
    """Filter candidate events for maritime security relevance."""
    if event_code and (event_code.startswith("18") or event_code.startswith("19") or event_code.startswith("17")):
        return True
    if quad_class is not None and quad_class >= 3:
        return True
    if url:
        url_lower = url.lower()
        if any(kw in url_lower for kw in MARITIME_KEYWORDS):
            return True
    return False


def calculate_chokepoint_disruptions(db_url: str | None = None) -> dict[str, Any]:
    """Calculate dynamic disruption scores and save relational evidence for all 13 maritime chokepoints."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    logger.info("Starting chokepoint disruption score calculation...")
    updated_count = 0
    now_utc = datetime.now(timezone.utc)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, name, lat, long, baseline_mbd FROM chokepoints;")
            chokepoints = cur.fetchall()

            for code, name, c_lat, c_long, mbd in chokepoints:
                c_lat_f, c_long_f = float(c_lat), float(c_long)

                # Query candidate events in geodesic bounding box over trailing 7 days
                cur.execute(
                    """
                    SELECT global_event_id, action_geo_lat, action_geo_long, num_mentions,
                           goldstein_scale, source_url, event_code, quad_class, event_date
                    FROM gdelt_events
                    WHERE action_geo_lat BETWEEN %s AND %s
                      AND action_geo_long BETWEEN %s AND %s
                      AND event_date >= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY num_mentions DESC
                    LIMIT 80;
                    """,
                    (c_lat_f - 3.0, c_lat_f + 3.0, c_long_f - 3.0, c_long_f + 3.0),
                )
                events = cur.fetchall()

                total_score = 0.0
                related_event_ids: list[int] = []
                last_reason = "Nominal transit — no proximate maritime threat events detected."

                for ev_id, ev_lat, ev_long, mentions, goldstein, url, ecode, quad, ev_date in events:
                    if ev_lat is None or ev_long is None:
                        continue

                    dist_km = haversine_distance_km(c_lat_f, c_long_f, float(ev_lat), float(ev_long))
                    if dist_km > 250.0:  # Geodesic radius threshold
                        continue

                    if not is_maritime_relevant(ecode, url, quad):
                        continue

                    severity = abs(float(goldstein or -5.0)) * 2.0  # Scale 0-20
                    mention_factor = min(4.0, float(mentions or 1) / 25.0)
                    proximity_decay = math.exp(-dist_km / 80.0)

                    event_impact = round((severity / 10.0) * mention_factor * proximity_decay * 10.0, 2)
                    total_score += event_impact
                    related_event_ids.append(ev_id)

                    reason_str = f"Kinetic/maritime event {ev_id} within {dist_km:.1f}km of {name} (impact +{event_impact:.1f})"
                    if event_impact >= 3.0:
                        last_reason = reason_str

                    # Save structured evidence to chokepoint_events child table
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

                final_score = min(100.0, max(0.0, round(total_score, 2)))

                # Exact canonical status thresholds
                if final_score >= 50.0:
                    status = "red"
                elif final_score >= 25.0:
                    status = "yellow"
                else:
                    status = "green"

                cur.execute(
                    """
                    UPDATE chokepoints
                    SET disruption_score = %s,
                        status = %s,
                        related_event_ids = %s,
                        last_disruption_reason = %s,
                        last_seen_at = NOW(),
                        updated_at = NOW()
                    WHERE code = %s;
                    """,
                    (final_score, status, Jsonb(related_event_ids[:10]), last_reason, code),
                )
                updated_count += 1

        conn.commit()

    logger.info(f"Chokepoint disruption engine completed: {updated_count} chokepoints updated.")
    return {"chokepoints_updated": updated_count}
