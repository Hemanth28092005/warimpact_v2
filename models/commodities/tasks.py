"""Celery tasks for commodity news pipeline."""

from __future__ import annotations

from celery import shared_task  # type: ignore[import-untyped]
from models.commodities.news import update_commodity_news


@shared_task(name="models.commodities.tasks.run_commodity_news_pipeline")
def run_commodity_news_pipeline() -> dict[str, int]:
    """15-min scheduled task for commodity news ingestion."""
    return update_commodity_news()
