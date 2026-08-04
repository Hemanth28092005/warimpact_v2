"""Celery tasks for Phase 3 Country Instability Index (CII) pipeline."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from celery import shared_task  # type: ignore[import-untyped]

from ingestion.common.logger import get_logger
from models.cii.worker import retrain_cii_pipeline_sync, run_cii_pipeline_sync

logger = get_logger(__name__)


@shared_task(name="models.cii.tasks.run_daily_cii_pipeline", bind=True, max_retries=3)  # type: ignore[misc]
def run_daily_cii_pipeline(self: Any, target_date_str: str | None = None) -> dict[str, Any]:
    """Celery periodic task executing daily CII calculation."""
    try:
        if target_date_str:
            target_date = date.fromisoformat(target_date_str)
        else:
            # Default to yesterday so country_daily_signals is fully ready
            target_date = datetime.now(timezone.utc).date() - timedelta(days=1)

        logger.info("celery_run_daily_cii_pipeline_triggered", extra={"target_date": str(target_date)})
        return run_cii_pipeline_sync(target_date=target_date)
    except Exception as exc:
        logger.error("celery_run_daily_cii_pipeline_failed", extra={"error": str(exc)})
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="models.cii.tasks.retrain_cii_monthly", bind=True, max_retries=2)  # type: ignore[misc]
def retrain_cii_monthly(self: Any) -> dict[str, Any]:
    """Celery periodic task executing monthly CII model retraining over trailing 12 months with regression guardrails."""
    try:
        logger.info("celery_retrain_cii_monthly_triggered")
        res = retrain_cii_pipeline_sync()
        logger.info("celery_retrain_cii_monthly_completed", extra=res)
        return res
    except Exception as exc:
        logger.error("celery_retrain_cii_monthly_failed", extra={"error": str(exc)})
        raise self.retry(exc=exc, countdown=300)
