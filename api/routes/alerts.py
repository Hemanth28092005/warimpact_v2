"""Alerts API route providing real-time aggregated geopolitical and systemic risk alerts."""

from __future__ import annotations

import datetime
from typing import Any, Literal
from fastapi import APIRouter, Query
from pydantic import BaseModel

from ingestion.common.db import open_async_connection

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertItem(BaseModel):
    id: str
    type: Literal["cii", "chokepoint", "flight", "seismic", "cascade", "protest", "trade"]
    level: Literal["critical", "warning", "info"]
    entity: str
    value: float
    message: str
    timestamp: str


@router.get("/recent", response_model=list[AlertItem])
async def get_recent_alerts(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum alerts to retrieve"),
) -> list[dict[str, Any]]:
    """Retrieve synthesized high-priority alerts across CII, chokepoints, seismic, unrest, and routes."""
    alerts: list[dict[str, Any]] = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            # 1. Critical Chokepoint Alerts
            await cur.execute(
                """
                SELECT code, name, disruption_score, status, last_disruption_reason, updated_at
                FROM chokepoints
                WHERE disruption_score >= 40 OR status IN ('critical', 'elevated')
                ORDER BY disruption_score DESC
                LIMIT 10;
                """
            )
            for r in await cur.fetchall():
                score = float(r[2])
                level = "critical" if score >= 70 or r[3] == "critical" else "warning"
                alerts.append(
                    {
                        "id": f"cjp_{r[0]}_{int(score)}",
                        "type": "chokepoint",
                        "level": level,
                        "entity": r[1],
                        "value": score,
                        "message": f"Chokepoint {r[1]} ({r[0]}) disruption index at {score:.0f}/100 [{r[3].upper()}]. {r[4] or 'Active maritime monitoring.'}",
                        "timestamp": r[5].isoformat() if hasattr(r[5], "isoformat") else now_iso,
                    }
                )

            # 2. High-Severity Civil Unrest / Protests
            await cur.execute(
                """
                SELECT id, location_name, state, country_code, event_severity, headline, event_date, validation_source
                FROM protests
                WHERE event_severity >= 55
                ORDER BY event_date DESC, event_severity DESC
                LIMIT 10;
                """
            )
            for r in await cur.fetchall():
                sev = float(r[4])
                level = "critical" if sev >= 70 else "warning"
                loc = f"{r[1]}, {r[2]}" if r[2] and r[1] != r[2] else (r[1] or r[3] or "Regional")
                src = f" [{r[7].upper()}]" if r[7] else ""
                alerts.append(
                    {
                        "id": f"protest_{r[0]}",
                        "type": "protest",
                        "level": level,
                        "entity": loc,
                        "value": sev,
                        "message": f"Unrest severity {sev:.0f}/100 in {loc}: {r[5]}{src}",
                        "timestamp": f"{r[6]}T12:00:00Z" if r[6] else now_iso,
                    }
                )

            # 3. High CII Volatility / Spikes
            await cur.execute(
                """
                SELECT DISTINCT ON (country_code)
                    country_code, cii_score, computed_at
                FROM country_instability_index
                WHERE cii_score >= 60 AND country_code <> 'IND'
                ORDER BY country_code, score_date DESC;
                """
            )
            for r in await cur.fetchall():
                score = float(r[1])
                level = "critical" if score >= 75 else "warning"
                alerts.append(
                    {
                        "id": f"cii_{r[0]}_{int(score)}",
                        "type": "cii",
                        "level": level,
                        "entity": r[0],
                        "value": score,
                        "message": f"Conflict Instability Index for {r[0]} elevated at {score:.1f}/100.",
                        "timestamp": r[2].isoformat() if hasattr(r[2], "isoformat") else now_iso,
                    }
                )

            # 4. Critical Seismic Events Near Maritime Corridors
            await cur.execute(
                """
                SELECT external_id, magnitude, place, near_chokepoint_code, distance_to_chokepoint_km, occurred_at
                FROM seismic_events
                WHERE magnitude >= 4.5 OR near_chokepoint_code IS NOT NULL
                ORDER BY occurred_at DESC
                LIMIT 8;
                """
            )
            for r in await cur.fetchall():
                mag = float(r[1])
                choke_info = f" ({r[4]:.0f}km from {r[3]})" if r[3] and r[4] is not None else ""
                alerts.append(
                    {
                        "id": f"quake_{r[0]}",
                        "type": "seismic",
                        "level": "critical" if mag >= 6.0 else "warning",
                        "entity": r[2] or "Offshore Sector",
                        "value": mag,
                        "message": f"M{mag:.1f} seismic event reported near {r[2] or 'coastal sector'}{choke_info}.",
                        "timestamp": r[5].isoformat() if hasattr(r[5], "isoformat") else now_iso,
                    }
                )

            # 5. Elevated Trade Route Risks
            await cur.execute(
                """
                SELECT id, commodity_code, partner_country, risk_score, primary_chokepoint
                FROM india_trade_routes
                WHERE risk_score >= 50
                ORDER BY risk_score DESC
                LIMIT 8;
                """
            )
            for r in await cur.fetchall():
                risk = float(r[3])
                alerts.append(
                    {
                        "id": f"route_{r[0]}",
                        "type": "trade",
                        "level": "critical" if risk >= 80 else "warning",
                        "entity": f"{r[1]} → {r[2]}",
                        "value": risk,
                        "message": f"High commodity supply chain exposure for {r[1]} corridor to {r[2]} (Risk: {risk:.1f}/100 via {r[4] or 'direct'}).",
                        "timestamp": now_iso,
                    }
                )

    # Sort alerts by severity level then value
    level_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda x: (level_order.get(x["level"], 3), -x["value"]))
    return alerts[:limit]
