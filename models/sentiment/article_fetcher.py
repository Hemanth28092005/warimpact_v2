"""Article text fetcher with sampling, caching, concurrency control, and trafilatura extraction."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx
from psycopg import AsyncConnection
import trafilatura

from ingestion.common.logger import get_logger

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

MAX_ARTICLE_CHARS = 2000
DEFAULT_CONCURRENCY = 10
DEFAULT_HOST_DELAY = 0.5


@dataclass(frozen=True)
class CachedArticle:
    source_url: str
    fetch_status: str
    article_text: str | None
    text_length: int


@dataclass(frozen=True)
class SampledEvent:
    global_event_id: int
    event_date: date
    country_code: str
    quad_class: int | None
    goldstein_scale: float | None
    avg_tone: float | None
    num_mentions: int | None
    source_url: str


async def sample_events_for_fetching(
    conn: AsyncConnection,
    target_date: date,
    sample_ratio: float = 0.10,
) -> list[SampledEvent]:
    """Sample ~10% of day's events per country, prioritizing quad_class >= 3, deduped by source_url."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT global_event_id, event_date,
                   COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code) AS country_code,
                   quad_class, goldstein_scale, avg_tone, num_mentions, source_url
            FROM gdelt_events
            WHERE event_date = %s AND source_url IS NOT NULL AND source_url != ''
            ORDER BY COALESCE(action_geo_country_code, actor1_country_code, actor2_country_code), global_event_id
            """,
            (target_date,),
        )
        rows = await cur.fetchall()

    if not rows:
        return []

    events_by_country: dict[str, list[SampledEvent]] = defaultdict(list)
    for r in rows:
        country = r[2] or "UNKNOWN"
        events_by_country[country].append(
            SampledEvent(
                global_event_id=r[0],
                event_date=r[1],
                country_code=country,
                quad_class=r[3],
                goldstein_scale=float(r[4]) if r[4] is not None else None,
                avg_tone=float(r[5]) if r[5] is not None else None,
                num_mentions=r[6],
                source_url=r[7],
            )
        )

    sampled: list[SampledEvent] = []
    seen_urls: set[str] = set()

    for country, country_events in events_by_country.items():
        # Sort prioritizing quad_class >= 3, then num_mentions DESC
        sorted_events = sorted(
            country_events,
            key=lambda e: (e.quad_class is not None and e.quad_class >= 3, e.num_mentions or 0),
            reverse=True,
        )
        target_unique_urls = max(1, int(len(sorted_events) * sample_ratio))
        country_selected = 0

        for event in sorted_events:
            if event.source_url not in seen_urls:
                seen_urls.add(event.source_url)
                sampled.append(event)
                country_selected += 1
                if country_selected >= target_unique_urls:
                    break

    logger.info(
        "sampled_events_selected",
        extra={
            "target_date": str(target_date),
            "total_events": len(rows),
            "sampled_count": len(sampled),
            "unique_urls": len(seen_urls),
        },
    )
    return sampled


async def get_cached_articles(
    conn: AsyncConnection,
    urls: list[str],
) -> dict[str, CachedArticle]:
    """Retrieve existing cached URL fetch results from article_text_cache."""
    if not urls:
        return {}

    cached: dict[str, CachedArticle] = {}
    # Batch query in chunks of 500
    for i in range(0, len(urls), 500):
        batch = urls[i : i + 500]
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT source_url, fetch_status, article_text, text_length
                FROM article_text_cache
                WHERE source_url = ANY(%s)
                """,
                (batch,),
            )
            rows = await cur.fetchall()
            for r in rows:
                cached[r[0]] = CachedArticle(
                    source_url=r[0],
                    fetch_status=r[1],
                    article_text=r[2],
                    text_length=r[3],
                )
    return cached


class RateLimitedFetcher:
    """Async HTTP fetcher enforcing global concurrency limit and per-host delay."""

    def __init__(
        self,
        max_concurrency: int = DEFAULT_CONCURRENCY,
        host_delay: float = DEFAULT_HOST_DELAY,
    ) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.host_delay = host_delay
        self.last_fetch_times: dict[str, float] = {}

    async def fetch_url(self, client: httpx.AsyncClient, url: str) -> CachedArticle:
        host = urlparse(url).netloc.lower()

        async with self.semaphore:
            # Per-host throttling
            now = time.monotonic()
            last_time = self.last_fetch_times.get(host, 0.0)
            wait_time = self.host_delay - (now - last_time)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_fetch_times[host] = time.monotonic()

            return await _do_fetch_and_extract(client, url)


async def _do_fetch_and_extract(client: httpx.AsyncClient, url: str) -> CachedArticle:
    """Fetch URL with 1 retry on transient errors and extract main text via trafilatura."""
    for attempt in range(2):
        try:
            resp = await client.get(url, timeout=8.0, follow_redirects=True)
            if resp.status_code == 403:
                return CachedArticle(url, "blocked", None, 0)
            if resp.status_code == 404:
                return CachedArticle(url, "dead", None, 0)
            if resp.status_code >= 500 and attempt == 0:
                await asyncio.sleep(1.0)
                continue
            resp.raise_for_status()

            html = resp.text
            extracted = trafilatura.extract(html) if html else None
            if not extracted or len(extracted.strip()) < 20:
                return CachedArticle(url, "no_content", None, 0)

            clean_text = extracted.strip()[:MAX_ARTICLE_CHARS]
            return CachedArticle(url, "success", clean_text, len(clean_text))

        except httpx.TimeoutException:
            return CachedArticle(url, "timeout", None, 0)
        except (httpx.ConnectError, httpx.HTTPError) as exc:
            if attempt == 0 and ("500" in str(exc) or "reset" in str(exc)):
                await asyncio.sleep(1.0)
                continue
            return CachedArticle(url, "dead", None, 0)
        except Exception:
            return CachedArticle(url, "dead", None, 0)

    return CachedArticle(url, "dead", None, 0)


async def fetch_and_cache_articles(
    conn: AsyncConnection,
    urls: list[str],
    max_concurrency: int = DEFAULT_CONCURRENCY,
    host_delay: float = DEFAULT_HOST_DELAY,
) -> dict[str, CachedArticle]:
    """Check cache, fetch uncached URLs asynchronously, store in DB, and return all articles."""
    if not urls:
        return {}

    existing_cache = await get_cached_articles(conn, urls)
    uncached_urls = [u for u in urls if u not in existing_cache]

    if not uncached_urls:
        logger.info("all_urls_served_from_cache", extra={"count": len(urls)})
        return existing_cache

    fetcher = RateLimitedFetcher(max_concurrency=max_concurrency, host_delay=host_delay)
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(headers=headers, verify=False) as client:
        tasks = [fetcher.fetch_url(client, url) for url in uncached_urls]
        newly_fetched = await asyncio.gather(*tasks)

    # Save newly fetched results to DB
    new_articles_map: dict[str, CachedArticle] = {}
    async with conn.cursor() as cur:
        for article in newly_fetched:
            new_articles_map[article.source_url] = article
            await cur.execute(
                """
                INSERT INTO article_text_cache (source_url, fetch_status, article_text, text_length, fetched_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_url) DO UPDATE SET
                    fetch_status = EXCLUDED.fetch_status,
                    article_text = EXCLUDED.article_text,
                    text_length = EXCLUDED.text_length,
                    fetched_at = EXCLUDED.fetched_at
                """,
                (
                    article.source_url,
                    article.fetch_status,
                    article.article_text,
                    article.text_length,
                    datetime.now(timezone.utc),
                ),
            )
    await conn.commit()

    success_count = sum(1 for a in newly_fetched if a.fetch_status == "success")
    success_rate = (success_count / len(newly_fetched)) if newly_fetched else 0.0

    logger.info(
        "article_fetch_completed",
        extra={
            "total_requested": len(urls),
            "cache_hits": len(existing_cache),
            "newly_fetched": len(newly_fetched),
            "success_count": success_count,
            "success_rate_pct": round(success_rate * 100, 2),
        },
    )

    combined = {**existing_cache, **new_articles_map}
    return combined
