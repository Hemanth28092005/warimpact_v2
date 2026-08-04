"""Maritime Chokepoint Disruption Scoring Engine.

Formula & Methodology:
- Disruption Score (0-100) is a derived geospatial estimate based on proximate GDELT kinetic/security event severity
  and mention volume within a ~2.5-degree (~250km) radius of the chokepoint coordinates.
- Formula:
  disruption_score = min(100.0, sum( (event_severity / 10.0) * (num_mentions / 50.0) * exp(-distance_km / 100.0) ))
- Status thresholds:
  - green: score < 20.0 (Nominal transit status)
  - yellow: 20.0 <= score < 50.0 (Elevated threat / regional tension)
  - red: score >= 50.0 (Critical disruption / active kinetic block)
"""

import math
import logging
from typing import Any
import psycopg
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)

DB_URL = "user=war_impact password=war_impact_password dbname=war_impact host=localhost port=5432"


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Great-Circle distance between two points in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def calculate_chokepoint_disruptions() -> dict[str, Any]:
    """Calculate dynamic disruption scores for all 13 maritime chokepoints.
    
    Upserts results into chokepoints table.
    """
    logger.info("Starting chokepoint disruption score calculation...")
    updated_count = 0

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, name, lat, long, baseline_mbd FROM chokepoints;")
            chokepoints = cur.fetchall()

            for code, name, c_lat, c_long, mbd in chokepoints:
                c_lat_f, c_long_f = float(c_lat), float(c_long)

                # Query GDELT events in the bounding box (+/- 2.5 degrees) over trailing 7 days
                cur.execute(
                    """
                    SELECT global_event_id, action_geo_lat, action_geo_long, num_mentions, goldstein_scale, source_url
                    FROM gdelt_events
                    WHERE action_geo_lat BETWEEN %s AND %s
                      AND action_geo_long BETWEEN %s AND %s
                      AND event_date >= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY num_mentions DESC
                    LIMIT 50;
                    """,
                    (c_lat_f - 2.5, c_lat_f + 2.5, c_long_f - 2.5, c_long_f + 2.5),
                )
                events = cur.fetchall()

                total_score = 0.0
                related_event_ids = []
                last_reason = "Nominal transit — no proximate threat events."

                for ev_id, ev_lat, ev_long, mentions, goldstein, url in events:
                    if ev_lat is None or ev_long is None:
                        continue

                    dist_km = haversine_distance_km(c_lat_f, c_long_f, float(ev_lat), float(ev_long))
                    severity = abs(float(goldstein or -5.0)) * 2.0  # Scale 0-20
                    mentions_weight = min(5.0, float(mentions or 1) / 50.0)
                    proximity_decay = math.exp(-dist_km / 100.0)

                    event_impact = (severity / 10.0) * mentions_weight * proximity_decay
                    total_score += event_impact
                    related_event_ids.append(ev_id)

                    if event_impact > 5.0:
                        last_reason = f"Security event {ev_id} within {dist_km:.1f}km of {name}"

                final_score = min(100.0, round(total_score, 2))

                if final_score >= 50.0:
                    status = "red"
                elif final_score >= 20.0:
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
                        updated_at = NOW()
                    WHERE code = %s;
                    """,
                    (final_score, status, Jsonb(related_event_ids[:10]), last_reason, code),
                )
                updated_count += 1
                logger.info(f"Chokepoint {code} ({name}): score={final_score}, status={status}")

        conn.commit()

    return {"chokepoints_updated": updated_count}
