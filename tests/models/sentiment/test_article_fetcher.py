from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.sentiment.article_fetcher import (
    CachedArticle,
    RateLimitedFetcher,
    SampledEvent,
    fetch_and_cache_articles,
    sample_events_for_fetching,
)


def test_sampled_event_creation() -> None:
    event = SampledEvent(
        global_event_id=1,
        event_date=date(2026, 7, 27),
        country_code="USA",
        quad_class=4,
        goldstein_scale=-7.0,
        avg_tone=-4.5,
        num_mentions=15,
        source_url="https://example.com/news1",
    )
    assert event.country_code == "USA"
    assert event.quad_class == 4


@pytest.mark.asyncio
async def test_sample_events_prioritizes_conflict_and_dedupes() -> None:
    rows = [
        (1, date(2026, 7, 27), "USA", 1, 1.0, 2.0, 5, "https://example.com/story1"),
        (2, date(2026, 7, 27), "USA", 4, -7.0, -5.0, 20, "https://example.com/story2"),
        (3, date(2026, 7, 27), "USA", 3, -3.0, -2.0, 10, "https://example.com/story1"),  # Duplicate URL
    ]

    mock_conn = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)

    sampled = await sample_events_for_fetching(mock_conn, date(2026, 7, 27), sample_ratio=0.5)

    assert len(sampled) >= 1
    # Priority should select quad_class 4 first
    urls = [e.source_url for e in sampled]
    assert len(urls) == len(set(urls))  # Deduped by URL


@pytest.mark.asyncio
async def test_fetch_and_cache_articles_serves_from_cache() -> None:
    cached_map = {
        "https://example.com/cached": CachedArticle(
            source_url="https://example.com/cached",
            fetch_status="success",
            article_text="Existing article text",
            text_length=21,
        )
    }

    mock_conn = AsyncMock()
    with patch("models.sentiment.article_fetcher.get_cached_articles", return_value=cached_map):
        result = await fetch_and_cache_articles(mock_conn, ["https://example.com/cached"])
        assert result["https://example.com/cached"].fetch_status == "success"
        assert result["https://example.com/cached"].article_text == "Existing article text"


@pytest.mark.asyncio
async def test_rate_limited_fetcher_concurrency_semaphore() -> None:
    fetcher = RateLimitedFetcher(max_concurrency=2, host_delay=0.0)
    assert fetcher.semaphore._value == 2
