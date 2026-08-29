"""Sage — Geopolitical Intelligence & Strategic Advisory Chatbot service.

Powered by OpenRouter with NVIDIA Nemotron 70B (nvidia/llama-3.1-nemotron-70b-instruct),
with automatic fallback to Google Gemini 2.0 Flash and offline telemetry synthesis.

Telemetry sources:
- Country Instability Index (CII) & Global DEFCON calculation
- 13 Maritime Chokepoint Disruption Scores & Statuses
- Country Bilateral Aggression Matrices (GDELT-derived 365d)
- India & Global High-Risk Trade Routes & Strategic Commodities
- Active Naval Carrier Strike Groups & Critical Fleet Deployments
- Civil Unrest & ACLED Protests
- Regional Security Headlines & Government Policy Actions
- Geopolitical Prediction Markets (Polymarket / Kalshi)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
import httpx
from ingestion.common.db import open_async_connection

load_dotenv()

logger = logging.getLogger("sage")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_openrouter_api_key() -> str:
    load_dotenv()
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def get_openrouter_model() -> str:
    load_dotenv()
    return os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b").strip()


def get_gemini_api_key() -> str:
    load_dotenv()
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_gemini_model() -> str:
    load_dotenv()
    return os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

REQUEST_TIMEOUT = httpx.Timeout(35.0, connect=10.0)

# Known entity aliases -> canonical lookup keys used for deep-dive context
ENTITY_ALIASES: dict[str, str] = {
    "hormuz": "HORMUZ",
    "strait of hormuz": "HORMUZ",
    "bab-el-mandeb": "BAB_EL_MANDEB",
    "bab el mandeb": "BAB_EL_MANDEB",
    "red sea": "BAB_EL_MANDEB",
    "malacca": "MALACCA",
    "strait of malacca": "MALACCA",
    "suez": "SUEZ",
    "suez canal": "SUEZ",
    "panama": "PANAMA",
    "panama canal": "PANAMA",
    "bosphorus": "BOSPHORUS",
    "taiwan": "TWN",
    "taiwan strait": "TWN",
    "israel": "ISR",
    "iran": "IRN",
    "russia": "RUS",
    "ukraine": "UKR",
    "india": "IND",
    "pakistan": "PAK",
    "china": "CHN",
    "usa": "USA",
    "united states": "USA",
    "syria": "SYR",
    "yemen": "YEM",
    "sudan": "SDN",
    "brent crude": "PETROLEUM_CRUDE",
    "crude oil": "PETROLEUM_CRUDE",
    "oil": "PETROLEUM_CRUDE",
    "lng": "LNG",
    "natural gas": "LNG",
    "fertilizer": "FERTILIZERS",
    "gold": "GOLD",
}

SUGGESTION_CATEGORIES = [
    {
        "category": "Crisis & Conflict Analysis",
        "emoji": "🔴",
        "prompts": [
            "What are the most volatile conflict flashpoints globally right now?",
            "Analyze current Israel-Iran escalation vectors and regional contagion risks.",
            "What is the bilateral aggression posture between Russia and NATO states?",
        ],
    },
    {
        "category": "Maritime Chokepoint Disruption",
        "emoji": "🚢",
        "prompts": [
            "What is the current disruption status across all 13 maritime chokepoints?",
            "What happens to global shipping if the Strait of Hormuz is closed?",
            "How severe are security threats in the Red Sea and Bab-el-Mandeb?",
        ],
    },
    {
        "category": "Commodities, Energy & Trade Impact",
        "emoji": "🛢️",
        "prompts": [
            "How vulnerable are India's crude oil import routes to Middle East tensions?",
            "What are the highest-risk trade routes and critical commodities right now?",
            "Analyze the impact of LNG supply corridor disruptions on European markets.",
        ],
    },
    {
        "category": "Strategic Advisory & Risk Hedging",
        "emoji": "🛡️",
        "prompts": [
            "Give actionable supply chain hedging advice for maritime freight operators.",
            "What contingency measures should energy import desks take today?",
            "Provide a geopolitical risk briefing for international travelers in the Levant.",
        ],
    },
    {
        "category": "Contagion & Platform Data",
        "emoji": "🌐",
        "prompts": [
            "Explain the current global DEFCON level and what telemetry triggers it.",
            "How is the Country Instability Index (CII) calculated by the platform models?",
            "What do prediction markets say about imminent geopolitical conflict odds?",
        ],
    },
]


def calculate_defcon(avg_cii: float | None) -> int:
    """Calculate DEFCON level 1-5 from global average Country Instability Index."""
    if avg_cii is None:
        return 3
    if avg_cii >= 65.0:
        return 1
    if avg_cii >= 55.0:
        return 2
    if avg_cii >= 45.0:
        return 3
    if avg_cii >= 35.0:
        return 4
    return 5


@dataclass
class TelemetrySnapshot:
    defcon_level: int = 3
    global_avg_cii: float | None = None
    top_volatile_countries: list[dict[str, Any]] = field(default_factory=list)
    chokepoints: list[dict[str, Any]] = field(default_factory=list)
    top_aggression_pairs: list[dict[str, Any]] = field(default_factory=list)
    high_risk_trade_routes: list[dict[str, Any]] = field(default_factory=list)
    active_naval_fleets: list[dict[str, Any]] = field(default_factory=list)
    recent_headlines: list[dict[str, Any]] = field(default_factory=list)
    recent_government_actions: list[dict[str, Any]] = field(default_factory=list)
    recent_protests: list[dict[str, Any]] = field(default_factory=list)
    prediction_markets: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Render a dense, structured, LLM-readable ground-truth context block."""
        lines: list[str] = [
            "## LIVE PLATFORM TELEMETRY (AUTHORITATIVE GROUND TRUTH)",
            f"- System DEFCON Alert Status: DEFCON {self.defcon_level}",
        ]
        if self.global_avg_cii is not None:
            lines.append(f"- Global Average Country Instability Index (CII): {self.global_avg_cii:.1f}/100")

        if self.top_volatile_countries:
            lines.append("- Top Volatile Countries (CII Scores [0-100 scale, higher=more unstable]):")
            for c in self.top_volatile_countries[:8]:
                low = c.get("ci_low")
                high = c.get("ci_high")
                ci_str = f" [CI: {low:.0f}-{high:.0f}]" if low is not None and high is not None else ""
                lines.append(f"  • {c.get('country_code')}: CII {c.get('cii_score', 0):.1f}/100{ci_str}")

        if self.chokepoints:
            lines.append("- Monitored Global Maritime Chokepoints (Disruption [0-100], Status, Baseline Transit):")
            for cp in self.chokepoints[:13]:
                disr = cp.get("disruption_score", 0)
                st = cp.get("status", "green").upper()
                mbd = cp.get("baseline_mbd", 0)
                reason = f" - Reason: {cp.get('last_disruption_reason')}" if cp.get("last_disruption_reason") else ""
                lines.append(f"  • {cp.get('name')} ({cp.get('code')}): Disruption {disr:.0f}/100 [{st}] — {mbd:.1f} M bbl/day{reason}")

        if self.top_aggression_pairs:
            lines.append("- Highest Bilateral Aggression Pairs (GDELT 365d Trailing Severity [0-100 scale]):")
            for p in self.top_aggression_pairs[:8]:
                lines.append(f"  • {p.get('country_a')} ⇄ {p.get('country_b')}: Score {p.get('aggression_score', 0):.1f}/100 ({p.get('event_count', 0)} events)")

        if self.high_risk_trade_routes:
            lines.append("- Highest-Risk India Bilateral Trade Routes & Landing Ports:")
            for r in self.high_risk_trade_routes[:8]:
                choke = f" via {r.get('primary_chokepoint')}" if r.get('primary_chokepoint') else " (direct transit)"
                port = f" → ⚓ Landing Port: {r.get('dest_port_name')}" if r.get('dest_port_name') else ""
                lines.append(f"  • Partner: {r.get('partner_country')}{port} | Commodity: {r.get('commodity_code')}{choke} | Risk: {r.get('risk_score', 0):.1f}/100")

        if self.active_naval_fleets:
            lines.append("- Strategic Naval Deployments & Carrier Strike Groups:")
            for f_item in self.active_naval_fleets[:6]:
                lines.append(f"  • {f_item.get('name')} ({f_item.get('flag_country')}): {f_item.get('operational_area')} [{f_item.get('threat_level', 'elevated').upper()}] — {f_item.get('mission_brief', 'Active patrol')}")

        if self.recent_headlines:
            lines.append("- Top Regional Geopolitical & Security Headlines:")
            for h in self.recent_headlines[:6]:
                brief = f" — {h.get('llm_brief')}" if h.get("llm_brief") else ""
                lines.append(f"  • [{h.get('region', 'GLOBAL').upper()}] {h.get('headline')}{brief}")

        if self.recent_government_actions:
            lines.append("- Recent Official Government & Diplomatic Policy Actions:")
            for g in self.recent_government_actions[:4]:
                lines.append(f"  • [{g.get('action_type', 'policy').upper()}] {g.get('headline')}")

        if self.recent_protests:
            lines.append("- Recent Civil Unrest & ACLED Protests:")
            for pr in self.recent_protests[:4]:
                loc = pr.get("location_name") or pr.get("city") or "India"
                lines.append(f"  • {pr.get('headline')} (Location: {loc}, Severity: {pr.get('event_severity', 0):.1f})")

        if self.prediction_markets:
            lines.append("- Geopolitical Prediction Market Odds (Polymarket / Kalshi):")
            for pm in self.prediction_markets[:4]:
                prob = f"{(pm.get('yes_price', 0) * 100):.0f}% Yes" if pm.get("yes_price") is not None else "Active"
                lines.append(f"  • \"{pm.get('question')}\": {prob} (24h Vol: ${pm.get('volume_24h_usd', 0):,.0f})")

        if self.warnings:
            lines.append(f"- Note: Data streams temporarily offline: {', '.join(self.warnings)}")

        return "\n".join(lines)

    def highlights(self) -> list[dict[str, str]]:
        """Extract key highlight tags for the frontend."""
        tags = [{"label": "DEFCON", "value": f"DEFCON {self.defcon_level}"}]
        if self.global_avg_cii is not None:
            tags.append({"label": "Global Avg CII", "value": f"{self.global_avg_cii:.1f}/100"})
        if self.top_volatile_countries:
            top_c = self.top_volatile_countries[0]
            tags.append({"label": "Top Volatility", "value": f"{top_c.get('country_code')} ({top_c.get('cii_score', 0):.0f})"})
        if self.chokepoints:
            worst_cp = max(self.chokepoints, key=lambda x: x.get("disruption_score", 0), default=None)
            if worst_cp and worst_cp.get("disruption_score", 0) > 0:
                tags.append({"label": "Chokepoint Alert", "value": f"{worst_cp.get('name')} ({worst_cp.get('disruption_score', 0):.0f})"})
        if self.high_risk_trade_routes:
            worst_rt = self.high_risk_trade_routes[0]
            tags.append({"label": "Top Trade Risk", "value": f"{worst_rt.get('partner_country')} ({worst_rt.get('commodity_code')})"})
        return tags


# --------------------------------------------------------------------------
# Database Telemetry Fetchers
# --------------------------------------------------------------------------

async def build_telemetry_snapshot() -> TelemetrySnapshot:
    """Build a complete live telemetry snapshot from the platform database."""
    snap = TelemetrySnapshot()

    # 1. Country Instability Index
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT country_code, cii_score, confidence_interval_low, confidence_interval_high
                    FROM country_instability_index
                    WHERE score_date = (SELECT MAX(score_date) FROM country_instability_index)
                      AND country_code <> 'IND'
                    ORDER BY cii_score DESC
                    LIMIT 10
                    """
                )
                cii_rows = await cur.fetchall()
                snap.top_volatile_countries = [
                    {
                        "country_code": r[0],
                        "cii_score": float(r[1]),
                        "ci_low": float(r[2]) if r[2] is not None else None,
                        "ci_high": float(r[3]) if r[3] is not None else None,
                    }
                    for r in cii_rows
                ]
                if cii_rows:
                    snap.global_avg_cii = sum(r["cii_score"] for r in snap.top_volatile_countries) / len(cii_rows)
                    snap.defcon_level = calculate_defcon(snap.global_avg_cii)
    except Exception as e:
        logger.warning("Sage: CII query failed: %s", e)
        snap.warnings.append("country_instability_index")

    # 2. Maritime Chokepoints
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT code, name, disruption_score, status, baseline_mbd, last_disruption_reason
                    FROM chokepoints
                    ORDER BY disruption_score DESC, code ASC
                    """
                )
                cp_rows = await cur.fetchall()
                snap.chokepoints = [
                    {
                        "code": r[0],
                        "name": r[1],
                        "disruption_score": float(r[2]),
                        "status": r[3],
                        "baseline_mbd": float(r[4]),
                        "last_disruption_reason": r[5],
                    }
                    for r in cp_rows
                ]
    except Exception as e:
        logger.warning("Sage: Chokepoints query failed: %s", e)
        snap.warnings.append("chokepoints")

    # 3. Country Aggression Scores
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT country_a, country_b, aggression_score, event_count
                    FROM country_aggression_scores
                    WHERE data_source = 'gdelt_derived'
                    ORDER BY aggression_score DESC NULLS LAST, event_count DESC
                    LIMIT 10
                    """
                )
                aggr_rows = await cur.fetchall()
                snap.top_aggression_pairs = [
                    {
                        "country_a": r[0],
                        "country_b": r[1],
                        "aggression_score": float(r[2]) if r[2] is not None else 0.0,
                        "event_count": int(r[3]) if r[3] is not None else 0,
                    }
                    for r in aggr_rows
                ]
    except Exception as e:
        logger.warning("Sage: Aggression query failed: %s", e)
        snap.warnings.append("country_aggression_scores")

    # 4. India Trade Routes
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT partner_country, commodity_code, primary_chokepoint, risk_score, dest_lat, dest_long
                    FROM india_trade_routes
                    ORDER BY risk_score DESC
                    LIMIT 10
                    """
                )
                route_rows = await cur.fetchall()
                
                def _port_label(lat: float, lon: float) -> str:
                    if abs(lat - 22.45) < 0.2 and abs(lon - 69.80) < 0.2:
                        return "Vadinar Port (Gujarat)"
                    if abs(lat - 21.1086) < 0.2 and abs(lon - 72.6358) < 0.2:
                        return "Hazira / Surat Port (Gujarat)"
                    if abs(lat - 22.7441) < 0.2 and abs(lon - 69.7025) < 0.2:
                        return "Mundra Port (Gujarat)"
                    if abs(lat - 22.8360) < 0.2 and abs(lon - 70.2185) < 0.2:
                        return "Kandla Port (Gujarat)"
                    if abs(lat - 21.7000) < 0.2 and abs(lon - 72.5800) < 0.2:
                        return "Dahej Port & LNG Terminal (Gujarat)"
                    if abs(lat - 18.9500) < 0.2 and abs(lon - 72.9500) < 0.2:
                        return "Mumbai JNPT (Maharashtra)"
                    if abs(lat - 15.4167) < 0.2 and abs(lon - 73.8000) < 0.2:
                        return "Mormugao Port (Goa)"
                    if abs(lat - 9.9656) < 0.2 and abs(lon - 76.2711) < 0.2:
                        return "Cochin Port / Kochi LNG (Kerala)"
                    if abs(lat - 8.7533) < 0.2 and abs(lon - 78.1633) < 0.2:
                        return "Tuticorin Port (Tamil Nadu)"
                    if abs(lat - 13.0844) < 0.2 and abs(lon - 80.2980) < 0.2:
                        return "Chennai Port (Tamil Nadu)"
                    if abs(lat - 16.9890) < 0.2 and abs(lon - 82.2874) < 0.2:
                        return "Kakinada Port (Andhra Pradesh)"
                    if abs(lat - 17.6868) < 0.2 and abs(lon - 83.2986) < 0.2:
                        return "Visakhapatnam Port (Andhra Pradesh)"
                    if abs(lat - 20.2644) < 0.2 and abs(lon - 86.6085) < 0.2:
                        return "Paradip Port (Odisha)"
                    if abs(lat - 22.0333) < 0.2 and abs(lon - 88.0833) < 0.2:
                        return "Haldia / Kolkata Port (West Bengal)"
                    return "Indian Gateway Port"

                snap.high_risk_trade_routes = [
                    {
                        "partner_country": r[0],
                        "commodity_code": r[1],
                        "primary_chokepoint": r[2],
                        "risk_score": float(r[3]),
                        "dest_port_name": _port_label(float(r[4]), float(r[5])),
                    }
                    for r in route_rows
                ]
    except Exception as e:
        logger.warning("Sage: Trade routes query failed: %s", e)
        snap.warnings.append("india_trade_routes")

    # 5. Naval Fleets
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT name, flag_country, operational_area, threat_level, status, mission_brief
                    FROM naval_fleets
                    ORDER BY threat_level = 'critical' DESC, threat_level = 'elevated' DESC
                    LIMIT 8
                    """
                )
                fleet_rows = await cur.fetchall()
                snap.active_naval_fleets = [
                    {
                        "name": r[0],
                        "flag_country": r[1],
                        "operational_area": r[2],
                        "threat_level": r[3],
                        "status": r[4],
                        "mission_brief": r[5],
                    }
                    for r in fleet_rows
                ]
    except Exception as e:
        logger.warning("Sage: Naval fleets query failed: %s", e)

    # 6. Regional Headlines
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT region, headline, published_at, llm_brief
                    FROM regional_headlines
                    ORDER BY rank ASC
                    LIMIT 10
                    """
                )
                hd_rows = await cur.fetchall()
                snap.recent_headlines = [
                    {
                        "region": r[0],
                        "headline": r[1],
                        "published_at": str(r[2]) if r[2] else None,
                        "llm_brief": r[3],
                    }
                    for r in hd_rows
                ]
    except Exception as e:
        logger.warning("Sage: Headlines query failed: %s", e)

    # 7. Government Actions
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT headline, action_type, published_at, llm_brief
                    FROM government_actions
                    ORDER BY rank ASC
                    LIMIT 6
                    """
                )
                gov_rows = await cur.fetchall()
                snap.recent_government_actions = [
                    {
                        "headline": r[0],
                        "action_type": r[1],
                        "published_at": str(r[2]) if r[2] else None,
                        "llm_brief": r[3],
                    }
                    for r in gov_rows
                ]
    except Exception as e:
        logger.warning("Sage: Government actions query failed: %s", e)

    # 8. Civil Protests
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT headline, city, state, location_name, event_severity
                    FROM protests
                    ORDER BY CASE WHEN validation_source = 'acled' THEN 0 ELSE 1 END, event_date DESC
                    LIMIT 6
                    """
                )
                pr_rows = await cur.fetchall()
                snap.recent_protests = [
                    {
                        "headline": r[0],
                        "city": r[1],
                        "state": r[2],
                        "location_name": r[3],
                        "event_severity": float(r[4]),
                    }
                    for r in pr_rows
                ]
    except Exception as e:
        logger.warning("Sage: Protests query failed: %s", e)

    # 9. Prediction Markets
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT question, platform, yes_price, volume_24h_usd
                    FROM prediction_markets
                    ORDER BY volume_24h_usd DESC NULLS LAST
                    LIMIT 5
                    """
                )
                pm_rows = await cur.fetchall()
                snap.prediction_markets = [
                    {
                        "question": r[0],
                        "platform": r[1],
                        "yes_price": float(r[2]) if r[2] is not None else None,
                        "volume_24h_usd": float(r[3]) if r[3] is not None else 0.0,
                    }
                    for r in pm_rows
                ]
    except Exception as e:
        logger.warning("Sage: Prediction markets query failed: %s", e)

    return snap


def detect_entities(message: str) -> list[str]:
    """Detect known geopolitical entities, chokepoints, and commodities in a user message."""
    text_lower = message.lower()
    matched = set()
    for alias, canonical in ENTITY_ALIASES.items():
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, text_lower):
            matched.add(canonical)
    return list(matched)


async def fetch_entity_context(entities: list[str]) -> str:
    """Fetch deep-dive telemetry for specific entities detected in the user prompt."""
    if not entities:
        return ""

    details: list[str] = []
    try:
        async with open_async_connection() as conn:
            async with conn.cursor() as cur:
                for entity in entities:
                    # Chokepoints deep dive
                    await cur.execute(
                        """
                        SELECT code, name, disruption_score, status, baseline_mbd, last_disruption_reason
                        FROM chokepoints
                        WHERE code = %s OR UPPER(name) LIKE %s
                        """,
                        (entity, f"%{entity}%"),
                    )
                    cp = await cur.fetchone()
                    if cp:
                        details.append(
                            f"### Target Chokepoint: {cp[1]} ({cp[0]})\n"
                            f"- Status: {cp[3].upper()} | Disruption Score: {float(cp[2]):.1f}/100 | Baseline Volume: {float(cp[4]):.1f} MBD\n"
                            f"- Threat Summary: {cp[5] or 'Normal maritime passage'}"
                        )
                        # Check quakes near this chokepoint
                        try:
                            await cur.execute(
                                """
                                SELECT magnitude, place, occurred_at FROM seismic_events
                                WHERE near_chokepoint_code = %s AND occurred_at >= NOW() - INTERVAL '7 days'
                                ORDER BY magnitude DESC LIMIT 2
                                """,
                                (cp[0],),
                            )
                            quakes = await cur.fetchall()
                            if quakes:
                                q_str = ", ".join(f"M{float(q[0]):.1f} ({q[1]})" for q in quakes)
                                details.append(f"- Recent Proximate Seismic Activity: {q_str}")
                        except Exception:
                            pass

                    # Country deep dive (CII + Aggression + Cascade)
                    if len(entity) == 3 and entity.isupper():
                        try:
                            await cur.execute(
                                """
                                SELECT country_code, cii_score, score_date, feature_snapshot
                                FROM country_instability_index
                                WHERE country_code = %s
                                ORDER BY score_date DESC LIMIT 1
                                """,
                                (entity,),
                            )
                            c_row = await cur.fetchone()
                            if c_row:
                                details.append(
                                    f"### Target Country Intelligence: {c_row[0]}\n"
                                    f"- Latest CII Instability Score: {float(c_row[1]):.1f}/100 (as of {c_row[2]})"
                                )
                        except Exception:
                            pass

                        # Cascade contagion
                        try:
                            await cur.execute(
                                """
                                SELECT target_country, contagion_score, co_spike_count
                                FROM cascade_scores
                                WHERE source_country = %s AND window_days = 7
                                ORDER BY contagion_score DESC LIMIT 3
                                """,
                                (entity,),
                            )
                            cascades = await cur.fetchall()
                            if cascades:
                                c_str = ", ".join(f"{c[0]} (co-spike rate: {(float(c[1])*100):.0f}%)" for c in cascades)
                                details.append(f"- Empirical Cross-Border Spillover / Contagion Pairs: {c_str}")
                        except Exception:
                            pass

                    # Commodity deep dive
                    try:
                        await cur.execute(
                            """
                            SELECT partner_country, primary_chokepoint, risk_score
                            FROM india_trade_routes
                            WHERE commodity_code = %s
                            ORDER BY risk_score DESC LIMIT 3
                            """,
                            (entity,),
                        )
                        routes = await cur.fetchall()
                        if routes:
                            r_str = ", ".join(f"{r[0]} via {r[1] or 'Direct'} (Risk: {float(r[2]):.0f})" for r in routes)
                            details.append(f"### Tracked Commodity Supply Routes: {entity}\n- Top Exposure Routes: {r_str}")
                    except Exception:
                        pass

    except Exception as exc:
        logger.warning("Sage: Failed entity context lookup: %s", exc)

    return "\n\n".join(details)


# --------------------------------------------------------------------------
# System Prompt & LLM Client
# --------------------------------------------------------------------------

def build_system_prompt(telemetry: TelemetrySnapshot, entity_context: str) -> str:
    telemetry_block = telemetry.to_prompt_block()
    entity_block = f"\n\n## TARGETED ENTITY DEEP-DIVE TELEMETRY\n{entity_context}" if entity_context else ""

    return f"""You are **S.A.G.E** (Strategic Advisory & Geopolitical Evaluation AI), an elite intelligence & risk advisor.
You operate as the resident strategic intelligence advisor within the S.A.G.E Global Geopolitical Instability and Trade Impact Platform.

YOUR MISSION:
Deliver clear, deeply analytical, and actionable geopolitical intelligence, crisis risk assessments, supply chain exposure evaluations, and strategic advice to government analysts, corporate decision-makers, logistics planners, and individual citizens.

CORE OPERATIONAL PRINCIPLES:
1. **Grounded in Platform Telemetry**: Treat the platform data below as ground truth. Cite specific quantitative metrics (e.g. DEFCON level, CII scores, chokepoint disruption scores, aggression pairs, and trade route risk numbers) to back up your reasoning.
2. **Actionable Strategic Advisory**: Never stop at just describing the crisis; always provide practical, structured recommendations (e.g., supply chain hedging, alternative routing, maritime security measures, scenario contingencies).
3. **Intellectual Honesty & Anti-Hallucination**: If a specific country, event, or metric is not present in the platform telemetry, explicitly state: "Based on current platform feeds and telemetry ingested up to the present cycle, no such event/data is recorded." Do not fabricate unverified real-time military attacks or breaking news not corroborated by the data.
4. **Structured Markdown Presentation**: Use bold section headers, concise bullet points, structured tables when comparing countries or routes, and executive takeaway callouts.

{telemetry_block}
{entity_block}
"""


async def call_openrouter_nemotron(
    messages: list[dict[str, str]],
    model: str | None = None,
    api_key: str | None = None,
) -> tuple[str, str]:
    """Call OpenRouter with NVIDIA Nemotron models (with automatic fallback routing)."""
    key = api_key or get_openrouter_api_key()
    mdl = model or get_openrouter_model()
    if not key:
        raise ValueError("OPENROUTER_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "War Impact Platform - S.A.G.E AI",
    }
    
    # Nemotron fallback chain
    model_candidates = [mdl]
    for alt in ["nvidia/nemotron-3.5-lightning", "nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3-super-120b-a12b"]:
        if alt not in model_candidates:
            model_candidates.append(alt)

    payload = {
        "models": model_candidates,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1800,
        "include_reasoning": False,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            logger.warning("OpenRouter error: status %d, body: %s", resp.status_code, resp.text[:200])
            raise RuntimeError(f"OpenRouter returned HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        content = (msg.get("content") or msg.get("reasoning") or "").strip()
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        resolved_model = data.get("model", mdl)
        return content, f"OpenRouter ({resolved_model})"


async def call_gemini_fallback(
    system_prompt: str,
    history: list[dict[str, str]],
    user_prompt: str,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """Fallback to Google Gemini 2.0 Flash via REST API."""
    key = api_key or get_gemini_api_key()
    mdl = model or get_gemini_model()
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured")

    contents = []
    full_prompt = f"{system_prompt}\n\nUser Question: {user_prompt}"
    contents.append({"parts": [{"text": full_prompt}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1200,
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={key}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini returned HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def generate_offline_brief(user_prompt: str, telemetry: TelemetrySnapshot, entity_context: str) -> str:
    """Deterministic, telemetry-grounded fallback response when all LLM providers are offline."""
    top_c_str = ", ".join(f"{c['country_code']} ({c['cii_score']:.0f})" for c in telemetry.top_volatile_countries[:4]) or "Nominal"
    hot_cp = [cp for cp in telemetry.chokepoints if cp["disruption_score"] >= 30 or cp["status"] != "green"]
    cp_str = ", ".join(f"{cp['name']} ({cp['disruption_score']:.0f}/100 [{cp['status'].upper()}])" for cp in hot_cp) or "All corridors green"
    routes_str = ", ".join(f"{r['partner_country']} ({r['commodity_code']} Risk: {r['risk_score']:.0f})" for r in telemetry.high_risk_trade_routes[:3]) or "Standard routing"
    avg_cii_display = f"{telemetry.global_avg_cii:.1f}/100" if telemetry.global_avg_cii is not None else "N/A"

    return f"""### 🛡️ Sage Geopolitical Advisory Telemetry Briefing

**System Status**: Global **DEFCON {telemetry.defcon_level}** | Average Instability Index: **{avg_cii_display}**

#### 1. Strategic Flashpoints & Volatility Overview
- **Top Country Instability (CII)**: {top_c_str}
- **Elevated Maritime Corridors**: {cp_str}
- **High-Risk Supply Routes**: {routes_str}

#### 2. Targeted Telemetry Analysis
{entity_context if entity_context else 'No specific corridor or country entity was isolated in your query. Platform signals reflect cross-domain baseline monitoring across 38 target sovereign nations and 13 strategic maritime chokepoints.'}

#### 3. Actionable Risk Mitigation Guidelines
- **Supply Chain & Logistics**: Review alternative routing around elevated maritime chokepoints. Prioritize dynamic rerouting options via Cape of Good Hope if Red Sea/Bab-el-Mandeb disruptions persist above threshold 50.
- **Energy & Commodity Desks**: Maintain 15-30 day strategic inventory buffers for crude oil and LNG imports exposed to Middle East chokepoint transit.
- **Risk Assessment Protocol**: Monitor real-time telemetry spikes on the platform map and check active prediction market probability shifts.

*(Note: Response synthesized via local telemetry engine while external LLM channels are synchronizing.)*
"""


def extract_followups(user_prompt: str, reply: str, telemetry: TelemetrySnapshot) -> list[str]:
    """Generate dynamic, contextual follow-up questions for the user."""
    followups = []
    lower_p = user_prompt.lower()
    lower_r = reply.lower()

    if "hormuz" in lower_p or "hormuz" in lower_r or "oil" in lower_p or "crude" in lower_p:
        followups.append("How would a closure of Hormuz impact India's crude oil imports?")
        followups.append("What are the alternative trade routes bypassing the Strait of Hormuz?")
    elif "red sea" in lower_p or "bab-el-mandeb" in lower_p or "suez" in lower_p:
        followups.append("What is the current disruption score for Bab-el-Mandeb?")
        followups.append("How much does rerouting via Cape of Good Hope add to freight transit time?")
    elif "israel" in lower_p or "iran" in lower_p or "middle east" in lower_p:
        followups.append("What are the contagion co-spike rates between Israel, Iran, and Syria?")
        followups.append("What naval carrier strike groups are currently deployed in the region?")
    elif "defcon" in lower_p or "cii" in lower_p or "instability" in lower_p:
        followups.append("Which countries have the highest Country Instability Index (CII) today?")
        followups.append("How does the platform determine the global DEFCON level?")
    else:
        followups.append("What are the most critical geopolitical risks to global trade right now?")
        followups.append("Give me a risk briefing on current maritime chokepoint vulnerabilities.")
        followups.append("Explain the current global DEFCON level and underlying telemetry.")

    return followups[:3]


async def generate_sage_reply(
    history: list[dict[str, str]],
    user_message: str,
    telemetry: TelemetrySnapshot,
    entity_context: str,
) -> tuple[str, str]:
    """Orchestrate 3-tier LLM generation: OpenRouter Nemotron -> Gemini Flash -> Offline synthesis."""
    system_prompt = build_system_prompt(telemetry, entity_context)
    
    chat_messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-6:]:  # Last 3 turns max
        chat_messages.append({"role": msg["role"], "content": msg["content"]})
    chat_messages.append({"role": "user", "content": user_message})

    # Tier 1: OpenRouter Nemotron
    openrouter_key = get_openrouter_api_key()
    openrouter_model = get_openrouter_model()
    if openrouter_key:
        try:
            logger.info("Sage: Querying OpenRouter with model %s", openrouter_model)
            reply, resolved_model = await call_openrouter_nemotron(chat_messages, model=openrouter_model, api_key=openrouter_key)
            return reply, resolved_model
        except Exception as err:
            logger.warning("Sage: OpenRouter call failed (%s). Falling back to secondary provider.", err)

    # Tier 2: Google Gemini Flash
    gemini_key = get_gemini_api_key()
    gemini_model = get_gemini_model()
    if gemini_key:
        try:
            logger.info("Sage: Querying Gemini fallback (%s)", gemini_model)
            reply = await call_gemini_fallback(system_prompt, history, user_message, api_key=gemini_key)
            return reply, f"Gemini ({gemini_model})"
        except Exception as err:
            logger.warning("Sage: Gemini fallback failed (%s). Falling back to offline synthesis.", err)

    # Tier 3: Deterministic Grounded Telemetry Synthesis
    logger.info("Sage: Synthesizing offline telemetry brief.")
    reply = generate_offline_brief(user_message, telemetry, entity_context)
    return reply, "Sage Grounded Telemetry Engine (Offline)"
