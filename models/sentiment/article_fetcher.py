"""Article text fetcher with canonical URL deduplication, retry policies, and 14-day freshness."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
import httpx
from psycopg import AsyncConnection
import trafilatura

from ingestion.common.logger import get_logger
from ingestion.dashboard.url_normalizer import normalize_url

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

MAX_ARTICLE_CHARS = 2000
DEFAULT_CONCURRENCY = 10
DEFAULT_HOST_DELAY = 0.5
MAX_FETCH_ATTEMPTS = 3


@dataclass(frozen=True)
class CachedArticle:
    source_url: str
    fetch_status: str
    article_text: str | None
    text_length: int
    canonical_url: str = ""
    attempt_count: int = 0
    last_error: str | None = None
    next_retry_at: datetime | None = None
    last_success_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.canonical_url and self.source_url:
            object.__setattr__(self, "canonical_url", normalize_url(self.source_url))


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
    canonical_url: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_url and self.source_url:
            object.__setattr__(self, "canonical_url", normalize_url(self.source_url))


async def sample_events_for_fetching(
    conn: AsyncConnection,
    target_date: date,
    sample_ratio: float = 0.5,
) -> list[SampledEvent]:
    """Sample events prioritizing conflict classes and deduplicating by canonical URL."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT global_event_id, event_date, action_geo_country_code, quad_class,
                   goldstein_scale, avg_tone, num_mentions, source_url
            FROM gdelt_events
            WHERE event_date = %s
              AND source_url IS NOT NULL AND source_url != ''
            ORDER BY quad_class DESC, num_mentions DESC;
            """,
            (target_date,),
        )
        rows = await cur.fetchall()

    sampled: list[SampledEvent] = []
    seen_urls: set[str] = set()

    for r in rows:
        ev_id, ev_date, ccode, quad, goldstein, tone, mentions, s_url = r
        c_url = normalize_url(s_url)
        if c_url in seen_urls:
            continue
        seen_urls.add(c_url)
        sampled.append(
            SampledEvent(
                global_event_id=ev_id,
                event_date=ev_date,
                country_code=ccode or "UNKNOWN",
                quad_class=quad,
                goldstein_scale=float(goldstein) if goldstein is not None else None,
                avg_tone=float(tone) if tone is not None else None,
                num_mentions=mentions,
                source_url=s_url,
                canonical_url=c_url,
            )
        )

    target_count = max(1, int(len(sampled) * sample_ratio)) if sampled else 0
    return sampled[:target_count]


async def get_fresh_cached_articles(
    conn: AsyncConnection,
    raw_urls: list[str],
) -> dict[str, CachedArticle]:
    """Retrieve fresh, valid cached article text keyed by canonical URL.

    Freshness criteria:
    - fetch_status = 'success' AND last_success_at > NOW() - INTERVAL '14 days'
    - non-success records (blocked, dead, timeout) are returned only if not yet eligible for retry.
    """
    if not raw_urls:
        return {}

    canonical_map = {normalize_url(u): u for u in raw_urls}
    canonicals = list(canonical_map.keys())

    fresh_cache: dict[str, CachedArticle] = {}
    now_utc = datetime.now(timezone.utc)

    for i in range(0, len(canonicals), 500):
        batch = canonicals[i : i + 500]
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT source_url, canonical_url, fetch_status, article_text, text_length,
                       attempt_count, last_error, next_retry_at, last_success_at
                FROM article_text_cache
                WHERE canonical_url = ANY(%s)
                """,
                (batch,),
            )
            rows = await cur.fetchall()
            for r in rows:
                s_url, c_url, status, text, length, attempts, error, next_retry, last_success = r
                
                # Check freshness for success
                is_fresh_success = (
                    status == "success" 
                    and last_success is not None 
                    and (now_utc - last_success) <= timedelta(days=14)
                )

                # Check retry eligibility for failed records
                is_not_ready_for_retry = (
                    status != "success"
                    and next_retry is not None
                    and next_retry > now_utc
                )

                # Abandoned items whose retry attempts are exhausted
                is_abandoned = (
                    status in ("abandoned", "permanent_failure")
                    or ((attempts or 0) >= MAX_FETCH_ATTEMPTS and status != "success")
                )

                if is_fresh_success or is_not_ready_for_retry or is_abandoned:
                    fresh_cache[c_url] = CachedArticle(
                        source_url=s_url,
                        canonical_url=c_url,
                        fetch_status=status,
                        article_text=text,
                        text_length=length or 0,
                        attempt_count=attempts or 0,
                        last_error=error,
                        next_retry_at=next_retry,
                        last_success_at=last_success,
                    )

    return fresh_cache


# Backwards compatibility alias
get_cached_articles = get_fresh_cached_articles


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

    async def fetch_url(
        self,
        client: httpx.AsyncClient,
        raw_url: str,
        prior_attempts: int = 0,
    ) -> CachedArticle:
        canonical_url = normalize_url(raw_url)
        host = urlparse(canonical_url).netloc.lower()

        async with self.semaphore:
            now = time.monotonic()
            last_time = self.last_fetch_times.get(host, 0.0)
            wait_time = self.host_delay - (now - last_time)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_fetch_times[host] = time.monotonic()

            return await fetch_single_article(client, raw_url, prior_attempts)


async def fetch_single_article(
    client: httpx.AsyncClient,
    raw_url: str,
    prior_attempts: int = 0,
) -> CachedArticle:
    """Fetch article content, extract clean text, and record retry metadata with max attempts limit."""
    canonical_url = normalize_url(raw_url)
    now_utc = datetime.now(timezone.utc)
    new_attempts = prior_attempts + 1

    if new_attempts >= MAX_FETCH_ATTEMPTS:
        # Max attempts reached - abandon retries
        return CachedArticle(
            source_url=raw_url,
            canonical_url=canonical_url,
            fetch_status="abandoned",
            article_text=None,
            text_length=0,
            attempt_count=new_attempts,
            last_error=f"Max retry attempts ({MAX_FETCH_ATTEMPTS}) reached",
            next_retry_at=None,
            last_success_at=None,
        )

    try:
        resp = await client.get(canonical_url, timeout=8.0, follow_redirects=True)
        if resp.status_code == 403:
            return CachedArticle(
                source_url=raw_url,
                canonical_url=canonical_url,
                fetch_status="blocked",
                article_text=None,
                text_length=0,
                attempt_count=new_attempts,
                last_error="HTTP 403 Forbidden",
                next_retry_at=now_utc + timedelta(hours=24),  # 24h cooldown
            )
        if resp.status_code == 404:
            return CachedArticle(
                source_url=raw_url,
                canonical_url=canonical_url,
                fetch_status="dead",
                article_text=None,
                text_length=0,
                attempt_count=new_attempts,
                last_error="HTTP 404 Not Found",
                next_retry_at=now_utc + timedelta(days=7),  # 7-day TTL
            )

        resp.raise_for_status()

        html = resp.text
        extracted = trafilatura.extract(html) if html else None
        if not extracted or len(extracted.strip()) < 20:
            return CachedArticle(
                source_url=raw_url,
                canonical_url=canonical_url,
                fetch_status="no_content",
                article_text=None,
                text_length=0,
                attempt_count=new_attempts,
                last_error="Insufficient extracted text length",
                next_retry_at=now_utc + timedelta(days=3),
            )

        clean_text = extracted.strip()[:MAX_ARTICLE_CHARS]
        return CachedArticle(
            source_url=raw_url,
            canonical_url=canonical_url,
            fetch_status="success",
            article_text=clean_text,
            text_length=len(clean_text),
            attempt_count=0,
            last_error=None,
            next_retry_at=None,
            last_success_at=now_utc,
        )

    except httpx.TimeoutException:
        backoff_seconds = min(3600, (2 ** new_attempts) * 60)  # Exponential backoff
        return CachedArticle(
            source_url=raw_url,
            canonical_url=canonical_url,
            fetch_status="timeout",
            article_text=None,
            text_length=0,
            attempt_count=new_attempts,
            last_error="Request timeout",
            next_retry_at=now_utc + timedelta(seconds=backoff_seconds),
        )
    except Exception as exc:
        return CachedArticle(
            source_url=raw_url,
            canonical_url=canonical_url,
            fetch_status="failed",
            article_text=None,
            text_length=0,
            attempt_count=new_attempts,
            last_error=str(exc)[:250],
            next_retry_at=now_utc + timedelta(hours=2),
        )


async def fetch_and_cache_articles(
    conn: AsyncConnection,
    urls: list[str],
    max_concurrency: int = DEFAULT_CONCURRENCY,
    host_delay: float = DEFAULT_HOST_DELAY,
) -> dict[str, CachedArticle]:
    """Check cache by canonical URL, fetch uncached/expired URLs, store retry metadata, and return all articles."""
    if not urls:
        return {}

    existing_cache = await get_cached_articles(conn, urls)
    
    # Identify canonical URLs needing fetch
    urls_to_fetch: list[str] = []
    seen_canonicals: set[str] = set()

    for u in urls:
        c_url = normalize_url(u)
        if u not in existing_cache and c_url not in existing_cache and c_url not in seen_canonicals:
            seen_canonicals.add(c_url)
            urls_to_fetch.append(u)

    if not urls_to_fetch:
        return existing_cache

    fetcher = RateLimitedFetcher(max_concurrency=max_concurrency, host_delay=host_delay)
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(headers=headers, verify=False) as client:
        tasks = [fetcher.fetch_url(client, u) for u in urls_to_fetch]
        newly_fetched = await asyncio.gather(*tasks)

    # Upsert results into article_text_cache
    new_articles_map: dict[str, CachedArticle] = {}
    async with conn.cursor() as cur:
        for article in newly_fetched:
            new_articles_map[article.canonical_url] = article
            await cur.execute(
                """
                INSERT INTO article_text_cache (
                    source_url, canonical_url, fetch_status, article_text, text_length,
                    attempt_count, last_error, next_retry_at, last_success_at, fetched_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (canonical_url) DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    fetch_status = EXCLUDED.fetch_status,
                    article_text = EXCLUDED.article_text,
                    text_length = EXCLUDED.text_length,
                    attempt_count = EXCLUDED.attempt_count,
                    last_error = EXCLUDED.last_error,
                    next_retry_at = EXCLUDED.next_retry_at,
                    last_success_at = COALESCE(EXCLUDED.last_success_at, article_text_cache.last_success_at),
                    updated_at = NOW();
                """,
                (
                    article.source_url,
                    article.canonical_url,
                    article.fetch_status,
                    article.article_text,
                    article.text_length,
                    article.attempt_count,
                    article.last_error,
                    article.next_retry_at,
                    article.last_success_at,
                ),
            )
    await conn.commit()

    combined = {**existing_cache, **new_articles_map}
    return combined
