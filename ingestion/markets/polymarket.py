"""Polymarket geopolitical market odds ingestion via the public Gamma API.

Stores open markets tagged under geopolitics/war categories with their live
YES prices as crowd-sourced event probabilities.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

import re

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
KEYWORD_FILTERS = [r"\bwar\b", r"\biran\b", r"\bisrael\b", r"\bukraine\b", r"\brussia\b", r"\bchina\b", r"\btaiwan\b", r"\bceasefire\b", r"\belection\b", r"\bnato\b", r"\bgaza\b", r"\bmissile\b", r"\bsanctions\b", r"\binvade\b", r"\bnuclear\b"]
SPORTS_EXCLUSION = [r"\bvs\.?\b", r"\bmatch\b", r"\bcup\b", r"\bleague\b", r"\bchampionship\b", r"\bfc\b", r"\bnba\b", r"\bnfl\b", r"\besports?\b", r"\bcounter-?strike\b", r"\bdota\b", r"\bloL\b", r"\bfight\b"]


def _is_geopolitical(question: str) -> bool:
    lowered = question.lower()
    if any(re.search(p, lowered) for p in SPORTS_EXCLUSION):
        return False
    return any(re.search(p, lowered) for p in KEYWORD_FILTERS)


def fetch_markets(limit: int = 100, timeout_seconds: float = 15.0) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    params: dict[str, Any] = {
        "closed": "false",
        "active": "true",
        "limit": limit,
        "order": "volume24hr",
        "ascending": "false",
        "offset": 0,
    }
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        for page in range(3):
            params["offset"] = page * limit
            response = client.get(GAMMA_MARKETS_URL, params=params)
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            for m in batch:
                question = str(m.get("question") or "")
                slug = str(m.get("slug") or "")
                if not question or not slug:
                    continue
                if not _is_geopolitical(question):
                    continue
                yes_price = m.get("outcomePrices")
                price_val = None
                if isinstance(yes_price, str):
                    import json as _json

                    try:
                        arr = _json.loads(yes_price)
                        price_val = float(arr[0]) if arr else None
                    except (ValueError, TypeError, IndexError):
                        price_val = None
                elif isinstance(yes_price, list) and yes_price:
                    try:
                        price_val = float(yes_price[0])
                    except (TypeError, ValueError):
                        price_val = None
                end_date_raw = m.get("endDate")
                end_dt = None
                if isinstance(end_date_raw, str):
                    try:
                        end_dt = datetime.fromisoformat(end_date_raw.replace("Z", "+00:00"))
                    except ValueError:
                        end_dt = None
                markets.append(
                    {
                        "market_slug": slug,
                        "question": question,
                        "category": (m.get("category") or "geopolitics"),
                        "yes_price": price_val,
                        "volume_24h_usd": float(m.get("volume24hr") or 0),
                        "end_date": end_dt,
                        "url": f"https://polymarket.com/market/{slug}",
                    }
                )
            if len(batch) < limit:
                break
    deduped = {m["market_slug"]: m for m in markets}
    return sorted(deduped.values(), key=lambda m: m["volume_24h_usd"], reverse=True)[:60]


def upsert_markets(conn: psycopg.Connection, markets: list[dict[str, Any]]) -> int:
    inserted = 0
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        for m in markets:
            cur.execute(
                """
                INSERT INTO prediction_markets
                    (market_slug, question, platform, category, yes_price, volume_24h_usd, end_date, url, fetched_at)
                VALUES (%s, %s, 'polymarket', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (market_slug) DO UPDATE SET
                    question = EXCLUDED.question,
                    yes_price = EXCLUDED.yes_price,
                    volume_24h_usd = EXCLUDED.volume_24h_usd,
                    end_date = EXCLUDED.end_date,
                    url = EXCLUDED.url,
                    fetched_at = EXCLUDED.fetched_at
                """,
                (
                    m["market_slug"],
                    m["question"],
                    m["category"],
                    m["yes_price"],
                    m["volume_24h_usd"],
                    m["end_date"],
                    m["url"],
                    now,
                ),
            )
            inserted += 1
    return inserted


def run_prediction_markets_sync() -> dict[str, int]:
    settings = get_settings()
    markets = fetch_markets()
    if not markets:
        raise RuntimeError("polymarket gamma returned no matching geopolitical markets")
    with psycopg.connect(settings.psycopg_database_url) as conn:
        with conn.transaction():
            count = upsert_markets(conn, markets)
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM prediction_markets WHERE market_slug != ALL(%s)",
                    ([m["market_slug"] for m in markets],),
                )
                removed = cur.rowcount
    logger.info("prediction_markets_upserted", extra={"count": count, "removed": removed})
    return {"fetched": len(markets), "rows_upserted": count, "rows_removed": removed}
