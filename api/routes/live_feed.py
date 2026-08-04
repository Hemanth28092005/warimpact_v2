"""Live Escalation Feed API endpoint for regional conflict escalation events."""

from __future__ import annotations

import time
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ingestion.common.db import open_async_connection
from models.sentiment.escalation_fetcher import REGION_COUNTRY_MAPPING
from models.sentiment.scorer import compute_composite_historical_sentiment

router = APIRouter(prefix="/api/v1", tags=["live-feed"])

# Simple in-memory response cache (TTL: 60 seconds)
_FEED_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 60.0


class EscalationFeedItem(BaseModel):
    global_event_id: int
    event_date: str
    ingested_at: str | None
    source_url: str | None
    actor1_code: str | None
    actor2_code: str | None
    country_code: str | None
    event_code: str | None
    event_severity: float
    num_mentions: int
    related_mentions_count: int
    article_text: str | None
    fetch_status: str | None


class EscalationFeedResponse(BaseModel):
    region: str
    window_hours: int
    total_escalations: int
    items: list[EscalationFeedItem]


def _dedupe_and_format_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe near-duplicate events within ~2 hour windows for identical actor pairs & event codes."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}

    for ev in events:
        a1 = ev["actor1_code"] or ""
        a2 = ev["actor2_code"] or ""
        c1, c2 = min(a1, a2), max(a1, a2)
        code = ev["event_code"] or ""
        dt_key = str(ev["event_date"])

        key = (c1, c2, code, dt_key)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(ev)

    deduped_items = []
    for group in grouped.values():
        # Pick the highest mention count instance
        primary = max(group, key=lambda x: x["num_mentions"] or 0)
        primary["related_mentions_count"] = len(group)
        deduped_items.append(primary)

    # Sort newest first by ingested_at / event_date
    deduped_items.sort(key=lambda x: (x["ingested_at"] or x["event_date"]), reverse=True)
    return deduped_items


@router.get("/live-feed/{region}", response_model=EscalationFeedResponse)
async def get_live_escalation_feed(
    region: str,
    window_hours: int = Query(default=24, ge=1, le=8760),
    bypass_cache: bool = Query(default=False),
) -> dict[str, Any]:
    """Retrieve live high-severity escalation feed for a region (india, usa, europe, middle_east)."""
    norm_region = region.lower().strip()
    if norm_region not in REGION_COUNTRY_MAPPING:
        valid_regions = ", ".join(REGION_COUNTRY_MAPPING.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid region '{region}'. Must be one of: {valid_regions}",
        )

    cache_key = f"{norm_region}_{window_hours}"
    now_ts = time.time()

    if not bypass_cache and cache_key in _FEED_CACHE:
        cached_ts, cached_data = _FEED_CACHE[cache_key]
        if now_ts - cached_ts < CACHE_TTL_SECONDS:
            return cached_data

    target_countries = REGION_COUNTRY_MAPPING[norm_region]

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT g.global_event_id, g.event_date, g.ingested_at, g.source_url,
                       g.actor1_country_code, g.actor2_country_code, g.action_geo_country_code,
                       g.event_code, g.num_mentions, g.avg_tone, g.goldstein_scale, g.quad_class,
                       c.article_text, c.fetch_status
                FROM gdelt_events g
                LEFT JOIN article_text_cache c ON g.source_url = c.source_url
                WHERE (
                    g.action_geo_country_code = ANY(%s)
                    OR g.actor1_country_code = ANY(%s)
                    OR g.actor2_country_code = ANY(%s)
                  )
                  AND g.event_date >= (SELECT COALESCE(MAX(event_date), CURRENT_DATE) FROM gdelt_events) - (%s || ' hours')::INTERVAL
                ORDER BY g.event_date DESC, g.num_mentions DESC, g.global_event_id DESC
                LIMIT 500
                """,
                (target_countries, target_countries, target_countries, str(window_hours)),
            )
            rows = await cur.fetchall()

    raw_events = []
    for r in rows:
        avg_tone = float(r[9]) if r[9] is not None else None
        goldstein = float(r[10]) if r[10] is not None else None
        quad_class = int(r[11]) if r[11] is not None else None
        severity = compute_composite_historical_sentiment(avg_tone, goldstein, quad_class)

        if severity <= -0.5:
            raw_events.append({
                "global_event_id": r[0],
                "event_date": str(r[1]),
                "ingested_at": r[2].isoformat() if r[2] else None,
                "source_url": r[3],
                "actor1_code": r[4],
                "actor2_code": r[5],
                "country_code": r[6],
                "event_code": r[7],
                "event_severity": severity,
                "num_mentions": r[8] or 1,
                "article_text": r[12],
                "fetch_status": r[13],
            })

    items = _dedupe_and_format_events(raw_events)

    response_data = {
        "region": norm_region,
        "window_hours": window_hours,
        "total_escalations": len(items),
        "items": items,
    }

    _FEED_CACHE[cache_key] = (now_ts, response_data)
    return response_data
