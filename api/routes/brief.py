"""AI World Brief: LLM-synthesized global situation summary.

Aggregates the platform's latest signals (CII extremes, escalations,
chokepoint-adjacent seismic, top aggression pairs) and synthesizes a short
brief via Groq. Cached in-process for BRIEF_CACHE_TTL_SECONDS to respect
rate limits. Returns 503 with a clear message when no GROQ_API_KEY is set.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from ingestion.common.db import open_async_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/brief", tags=["AI Brief"])

BRIEF_CACHE_TTL_SECONDS = 900.0
_BRIEF_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "groq/compound-mini")


async def _gather_signals() -> dict[str, Any]:
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT country_code, cii_score FROM country_instability_index
                WHERE score_date = (SELECT MAX(score_date) FROM country_instability_index)
                  AND country_code <> 'IND'
                ORDER BY cii_score DESC LIMIT 5
                """
            )
            top_cii = [(r[0], float(r[1])) for r in await cur.fetchall()]

            await cur.execute(
                """
                SELECT country_a, country_b, aggression_score, event_count
                FROM country_aggression_scores
                WHERE data_source = 'gdelt_derived'
                ORDER BY aggression_score DESC NULLS LAST LIMIT 5
                """
            )
            top_aggression = [(r[0], r[1], float(r[2]), int(r[3])) for r in await cur.fetchall()]

            await cur.execute(
                """
                SELECT code, name, disruption_score, status FROM chokepoints
                WHERE status != 'green' OR disruption_score >= 40
                ORDER BY disruption_score DESC LIMIT 5
                """
            )
            hot_chokepoints = [(r[0], r[1], float(r[2]), r[3]) for r in await cur.fetchall()]

            await cur.execute(
                """
                SELECT magnitude, place FROM seismic_events
                WHERE near_chokepoint_code IS NOT NULL
                  AND occurred_at >= NOW() - interval '48 hours'
                ORDER BY magnitude DESC LIMIT 3
                """
            )
            chokepoint_quakes = [(float(r[0]), r[1]) for r in await cur.fetchall()]

            await cur.execute(
                """
                SELECT count(*) FROM gdelt_events
                WHERE event_date >= (SELECT MAX(event_date) FROM gdelt_events) - interval '24 hours'
                """
            )
            events_24h = int((await cur.fetchone())[0])

    return {
        "top_cii": top_cii,
        "top_aggression": top_aggression,
        "hot_chokepoints": hot_chokepoints,
        "chokepoint_quakes": chokepoint_quakes,
        "events_24h": events_24h,
    }


def _build_prompt(signals: dict[str, Any]) -> str:
    cii_lines = ", ".join(f"{c} {s:.0f}/100" for c, s in signals["top_cii"])
    aggr_lines = "; ".join(f"{a}->{b} score {s:.0f} ({e} events)" for a, b, s, e in signals["top_aggression"])
    choke_lines = "; ".join(f"{n} ({c}) disruption {d:.0f} [{st}]" for c, n, d, st in signals["hot_chokepoints"]) or "none elevated"
    quake_lines = "; ".join(f"M{m:.1f} near {p}" for m, p in signals["chokepoint_quakes"]) or "none"

    return (
        "You are a geopolitical intelligence analyst. Write a concise world situation brief "
        "(max 120 words, 3-5 sentences, factual and cautious tone). Use ONLY the data provided; "
        "do not invent events. Signal data:\n"
        f"- Highest instability (CII): {cii_lines}\n"
        f"- Top bilateral aggression (365d GDELT): {aggr_lines}\n"
        f"- Maritime chokepoints elevated: {choke_lines}\n"
        f"- Recent quakes near chokepoints: {quake_lines}\n"
        f"- GDELT event volume last 24h: {signals['events_24h']}\n"
        "Output plain text only, no markdown, no headings."
    )


@router.get("/world")
async def get_world_brief(bypass_cache: bool = False) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    cache_key = "world"
    now = time.time()
    if not bypass_cache and cache_key in _BRIEF_CACHE:
        ts, cached = _BRIEF_CACHE[cache_key]
        if now - ts < BRIEF_CACHE_TTL_SECONDS:
            return cached

    signals = await _gather_signals()
    prompt = _build_prompt(signals)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "You are a precise geopolitical analyst. Never fabricate events."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 300,
            },
        )
    if resp.status_code != 200:
        logger.warning("groq_brief_failed", extra={"status": resp.status_code})
        raise HTTPException(status_code=502, detail=f"LLM provider error {resp.status_code}")

    brief_text = resp.json()["choices"][0]["message"]["content"].strip()
    brief_text = re.sub(r"<think>.*?</think>", "", brief_text, flags=re.DOTALL).strip()
    payload = {
        "brief": brief_text,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "signals": {
            "top_cii": signals["top_cii"],
            "events_24h": signals["events_24h"],
            "hot_chokepoints": len(signals["hot_chokepoints"]),
        },
        "model": MODEL,
    }
    _BRIEF_CACHE[cache_key] = (now, payload)
    return payload
