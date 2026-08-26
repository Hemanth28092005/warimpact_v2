"""Shared Batch Evidence Service for Dashboard Data Layer.

Guarantees:
1. Batch article_text_cache lookups and async fetches outside of database write transactions.
2. Deduplication of canonical URLs in memory before network I/O.
3. Bounded concurrency, per-host throttling, and retry limits.
4. Returns a synchronous mapping `dict[canonical_url, CachedArticle]` to feed tasks.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Sequence
import httpx
import psycopg

from ingestion.common.config import get_settings
from ingestion.dashboard.url_normalizer import normalize_url
from models.sentiment.article_fetcher import (
    CachedArticle,
    fetch_single_article,
    DEFAULT_CONCURRENCY,
    DEFAULT_HOST_DELAY,
)

logger = logging.getLogger(__name__)


async def _fetch_missing_articles_async(
    missing_urls: list[tuple[str, str, int]],  # (raw_url, canonical_url, prior_attempts)
    max_concurrency: int = 15,
) -> dict[str, CachedArticle]:
    """Fetch missing eligible articles asynchronously with bounded concurrency."""
    if not missing_urls:
        return {}

    # Bound batch to top 75 candidate articles to keep latency minimal
    missing_batch = missing_urls[:75]
    results: dict[str, CachedArticle] = {}
    sem = asyncio.Semaphore(max_concurrency)

    async with httpx.AsyncClient(
        headers={"User-Agent": "WarImpactPlatform/1.0 (+https://warimpact.internal)"},
        follow_redirects=True,
        timeout=5.0,
    ) as client:
        async def _fetch_one(raw_url: str, canonical_url: str, prior_attempts: int) -> None:
            async with sem:
                try:
                    article = await fetch_single_article(
                        client,
                        raw_url,
                        prior_attempts=prior_attempts,
                    )
                    results[canonical_url] = article
                except Exception as exc:
                    logger.debug(f"Async fetch failed for {canonical_url}: {exc}")
                    results[canonical_url] = CachedArticle(
                        source_url=raw_url,
                        canonical_url=canonical_url,
                        fetch_status="failed",
                        article_text=None,
                        text_length=0,
                        attempt_count=prior_attempts + 1,
                        last_error=str(exc)[:500],
                        next_retry_at=None,
                    )

        tasks = [
            _fetch_one(raw_url, canonical_url, prior_attempts)
            for raw_url, canonical_url, prior_attempts in missing_batch
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results


def get_batch_article_evidence(
    urls: Sequence[str],
    db_url: str | None = None,
    allow_fetch: bool = True,
    max_concurrency: int = 15,
) -> dict[str, CachedArticle]:
    """Retrieve article evidence for a sequence of URLs, fetching eligible missing items.

    Executed outside of any feed transaction. Returns a map of canonical_url -> CachedArticle.
    """
    if not urls:
        return {}

    if not db_url:
        db_url = get_settings().psycopg_database_url

    # 1. Deduplicate and normalize in-memory
    url_map: dict[str, str] = {}  # canonical_url -> first raw_url
    for u in urls:
        if u and u.strip():
            c_url = normalize_url(u.strip())
            if c_url not in url_map:
                url_map[c_url] = u.strip()

    canonical_list = list(url_map.keys())
    if not canonical_list:
        return {}

    cached_evidence: dict[str, CachedArticle] = {}
    missing_for_fetch: list[tuple[str, str, int]] = []
    now = datetime.now(timezone.utc)

    # 2. Query cache
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_url, canonical_url, fetch_status, article_text, text_length,
                           attempt_count, last_error, next_retry_at, last_success_at
                    FROM article_text_cache
                    WHERE canonical_url = ANY(%s);
                    """,
                    (canonical_list,),
                )
                rows = cur.fetchall()

                found_canonicals: set[str] = set()
                for r in rows:
                    source_url, c_url, status, text, text_len, attempts, last_err, next_retry, last_succ = r
                    found_canonicals.add(c_url)
                    article = CachedArticle(
                        source_url=source_url,
                        canonical_url=c_url,
                        fetch_status=status,
                        article_text=text,
                        text_length=text_len or 0,
                        attempt_count=attempts or 0,
                        last_error=last_err,
                        next_retry_at=next_retry,
                        last_success_at=last_succ,
                    )
                    cached_evidence[c_url] = article

                    # Check if retry eligible
                    if status != "success" and status != "abandoned" and allow_fetch:
                        if next_retry is None or next_retry <= now:
                            missing_for_fetch.append((url_map[c_url], c_url, attempts or 0))

                for c_url in canonical_list:
                    if c_url not in found_canonicals and allow_fetch:
                        missing_for_fetch.append((url_map[c_url], c_url, 0))

    except Exception as exc:
        logger.warning(f"Failed to read article_text_cache in batch: {exc}")
        # Proceed with in-memory fallback
        if allow_fetch:
            for c_url in canonical_list:
                if c_url not in cached_evidence:
                    missing_for_fetch.append((url_map[c_url], c_url, 0))

    # 3. Asynchronously fetch missing/eligible articles if needed
    if missing_for_fetch and allow_fetch:
        logger.info(f"Batch fetching {len(missing_for_fetch)} eligible article texts...")
        try:
            fetched = asyncio.run(_fetch_missing_articles_async(missing_for_fetch, max_concurrency=max_concurrency))
            cached_evidence.update(fetched)

            # Persist newly fetched articles back to cache
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    for art in fetched.values():
                        cur.execute(
                            """
                            INSERT INTO article_text_cache (
                                source_url, canonical_url, fetch_status, article_text, text_length,
                                attempt_count, last_error, next_retry_at, last_success_at, fetched_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (source_url) DO UPDATE SET
                                canonical_url = EXCLUDED.canonical_url,
                                fetch_status = EXCLUDED.fetch_status,
                                article_text = COALESCE(EXCLUDED.article_text, article_text_cache.article_text),
                                text_length = CASE WHEN EXCLUDED.article_text IS NOT NULL THEN EXCLUDED.text_length ELSE article_text_cache.text_length END,
                                attempt_count = EXCLUDED.attempt_count,
                                last_error = EXCLUDED.last_error,
                                next_retry_at = EXCLUDED.next_retry_at,
                                last_success_at = COALESCE(EXCLUDED.last_success_at, article_text_cache.last_success_at),
                                fetched_at = NOW();
                            """,
                            (
                                art.source_url,
                                art.canonical_url,
                                art.fetch_status,
                                art.article_text,
                                art.text_length,
                                art.attempt_count,
                                art.last_error,
                                art.next_retry_at,
                                art.last_success_at,
                            ),
                        )
                conn.commit()
        except Exception as exc:
            logger.warning(f"Error during async batch article fetch/upsert: {exc}")

    return cached_evidence
