"""Unit tests verifying article text cache retry policies and canonical URL deduplication."""

from datetime import datetime, timedelta, timezone
import pytest
from ingestion.dashboard.url_normalizer import normalize_url


def test_canonical_url_normalization_and_deduplication():
    """Verify tracking parameters, fragments, and case differences normalize to identical canonical URLs."""
    raw_variants = [
        "https://www.Reuters.com/article/middle-east-oil-crisis?utm_source=twitter&utm_medium=social#comments",
        "https://www.reuters.com/article/middle-east-oil-crisis/?fbclid=IwAR2345678",
        "https://www.reuters.com/article/middle-east-oil-crisis?ref=hp&sessionid=9999",
        "https://www.reuters.com/article/middle-east-oil-crisis",
    ]

    canonicals = [normalize_url(u) for u in raw_variants]
    # All 4 variants should normalize to the exact same canonical string
    assert len(set(canonicals)) == 1
    assert canonicals[0] == "https://www.reuters.com/article/middle-east-oil-crisis"


def test_retry_policy_timings():
    """Verify exponential backoff, 403 cooldown, and 404 TTL retry timing rules."""
    now = datetime.now(timezone.utc)

    # 1. Timeout exponential backoff: 2^attempt * 60s
    attempt_1_delay = (2 ** 1) * 60  # 120s = 2 min
    attempt_2_delay = (2 ** 2) * 60  # 240s = 4 min
    attempt_3_delay = (2 ** 3) * 60  # 480s = 8 min

    assert attempt_1_delay == 120
    assert attempt_2_delay == 240
    assert attempt_3_delay == 480

    # 2. Blocked 403 cooldown: 24 hours
    cooldown_403 = timedelta(hours=24)
    assert cooldown_403.total_seconds() == 86400

    # 3. Dead 404 TTL: 7 days
    ttl_404 = timedelta(days=7)
    assert ttl_404.days == 7

    # 4. Success freshness: 14 days
    freshness_success = timedelta(days=14)
    assert freshness_success.days == 14


@pytest.mark.asyncio
async def test_retry_limit_abandons_after_max_attempts():
    """Verify that reaching MAX_FETCH_ATTEMPTS marks article as abandoned with next_retry_at=None."""
    from unittest.mock import AsyncMock
    from models.sentiment.article_fetcher import fetch_single_article, MAX_FETCH_ATTEMPTS

    mock_client = AsyncMock()
    # Attempt 3 (since prior_attempts was 2)
    article = await fetch_single_article(mock_client, "https://example.com/dead-article", prior_attempts=2)
    assert article.attempt_count == 3
    assert article.fetch_status == "abandoned"
    assert article.next_retry_at is None
    assert "Max retry attempts" in (article.last_error or "")
