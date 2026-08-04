"""Celery task wrappers for the sentiment and conflict signals pipeline."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from ingestion.common.celery_app import celery_app
from models.sentiment.worker import run_sentiment_pipeline_sync


@celery_app.task(  # type: ignore[misc]
    name="models.sentiment.tasks.run_daily_sentiment_pipeline",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_daily_sentiment_pipeline(self: Any, signal_date: str | None = None) -> dict[str, Any]:
    if signal_date:
        target_date = date.fromisoformat(signal_date)
    else:
        # Default to yesterday's date to allow full day ingestion to complete
        target_date = datetime.now(timezone.utc).date() - timedelta(days=1)

    return run_sentiment_pipeline_sync(target_date=target_date)


@celery_app.task(  # type: ignore[misc]
    name="models.sentiment.tasks.fetch_escalation_articles",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def fetch_escalation_articles(self: Any, lookback_minutes: int = 20) -> dict[str, Any]:
    import asyncio
    from models.sentiment.escalation_fetcher import fetch_escalation_article_text

    summary = asyncio.run(fetch_escalation_article_text(lookback_minutes=lookback_minutes))
    return {
        "lookback_minutes": summary.lookback_minutes,
        "matched_events_count": summary.matched_events_count,
        "unique_urls_count": summary.unique_urls_count,
        "cache_hits_count": summary.cache_hits_count,
        "new_fetches_attempted": summary.new_fetches_attempted,
        "successful_fetches": summary.successful_fetches,
    }


if __name__ == "__main__":
    print("Phase 2 Celery tasks ready")
