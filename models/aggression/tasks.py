"""Celery task for daily Bilateral Aggression Score pipeline execution."""

from __future__ import annotations

from typing import Any

from ingestion.common.celery_app import celery_app
from models.aggression.worker import run_aggression_pipeline_sync


@celery_app.task(name="models.aggression.tasks.run_daily_aggression_pipeline")
def run_daily_aggression_pipeline() -> dict[str, Any]:
    """Celery task executing daily Bilateral Aggression Score pipeline."""
    return run_aggression_pipeline_sync()
