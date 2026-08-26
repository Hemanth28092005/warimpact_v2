"""Live commodity futures price ingestion from the Yahoo Finance chart API.

Fetches delayed quotes for energy, metals, and agriculture futures relevant to
trade-impact analysis and upserts them into commodity_prices. Also ensures the
tracked_commodities reference rows exist so FK constraints hold.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

COMMODITY_SYMBOLS: list[dict[str, str]] = [
    {"code": "CRUDE_WTI", "symbol": "CL=F", "name": "Crude Oil WTI", "category": "energy", "unit": "USD/bbl"},
    {"code": "CRUDE_BRENT", "symbol": "BZ=F", "name": "Crude Oil Brent", "category": "energy", "unit": "USD/bbl"},
    {"code": "NATGAS", "symbol": "NG=F", "name": "Natural Gas", "category": "energy", "unit": "USD/MMBtu"},
    {"code": "GOLD", "symbol": "GC=F", "name": "Gold", "category": "metals", "unit": "USD/oz"},
    {"code": "COPPER", "symbol": "HG=F", "name": "Copper", "category": "metals", "unit": "USD/lb"},
    {"code": "WHEAT", "symbol": "ZW=F", "name": "Wheat", "category": "agriculture", "unit": "USc/bu"},
    {"code": "CORN", "symbol": "ZC=F", "name": "Corn", "category": "agriculture", "unit": "USc/bu"},
]

DATA_SOURCE = "YAHOO_FINANCE_DELAYED"


def ensure_tracked_commodities(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for item in COMMODITY_SYMBOLS:
            cur.execute(
                """
                INSERT INTO tracked_commodities (commodity_code, name, category, trade_type, annual_value_usd, source_citation)
                VALUES (%s, %s, %s, 'futures', 0, %s)
                ON CONFLICT (commodity_code) DO NOTHING
                """,
                (item["code"], item["name"], item["category"], f"{DATA_SOURCE} reference row; annual value not tracked"),
            )


def fetch_quote(client: httpx.Client, item: dict[str, str]) -> dict[str, Any] | None:
    response = client.get(YAHOO_CHART_URL.format(symbol=item["symbol"]))
    if response.status_code != 200:
        logger.warning("yahoo_quote_failed", extra={"symbol": item["symbol"], "status": response.status_code})
        return None
    results = response.json().get("chart", {}).get("result") or []
    if not results:
        return None
    meta = results[0].get("meta", {}) or {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        return None
    price_f = float(price)
    prev_f = float(prev) if prev is not None else None
    change_pct = ((price_f - prev_f) / prev_f * 100.0) if prev_f else None
    observed_epoch = meta.get("regularMarketTime")
    observed_at = (
        datetime.fromtimestamp(int(observed_epoch), tz=timezone.utc)
        if observed_epoch
        else datetime.now(timezone.utc)
    )
    return {
        "commodity_code": item["code"],
        "price_usd": price_f,
        "previous_close_usd": prev_f,
        "change_pct": change_pct,
        "unit_label": item["unit"],
        "observed_at": observed_at,
    }


def fetch_quotes(timeout_seconds: float = 15.0) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=BROWSER_HEADERS) as client:
        for item in COMMODITY_SYMBOLS:
            quote = fetch_quote(client, item)
            if quote is not None:
                quotes.append(quote)
    return quotes


def upsert_prices(conn: psycopg.Connection, prices: list[dict[str, Any]]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for p in prices:
            cur.execute(
                """
                INSERT INTO commodity_prices
                    (commodity_code, price_usd, previous_close_usd, change_pct, currency, unit_label, data_source, observed_at)
                VALUES (%s, %s, %s, %s, 'USD', %s, %s, %s)
                ON CONFLICT (commodity_code, observed_at, data_source) DO UPDATE SET
                    price_usd = EXCLUDED.price_usd,
                    previous_close_usd = EXCLUDED.previous_close_usd,
                    change_pct = EXCLUDED.change_pct
                """,
                (
                    p["commodity_code"],
                    p["price_usd"],
                    p["previous_close_usd"],
                    p["change_pct"],
                    p["unit_label"],
                    DATA_SOURCE,
                    p["observed_at"],
                ),
            )
            inserted += 1
    return inserted


def run_commodity_prices_sync() -> dict[str, int]:
    settings = get_settings()
    quotes = fetch_quotes()
    if not quotes:
        raise RuntimeError("yahoo finance returned no usable commodity quotes")
    with psycopg.connect(settings.psycopg_database_url) as conn:
        with conn.transaction():
            ensure_tracked_commodities(conn)
            count = upsert_prices(conn, quotes)
    logger.info("commodity_prices_upserted", extra={"count": count})
    return {"quotes_fetched": len(quotes), "rows_upserted": count}
