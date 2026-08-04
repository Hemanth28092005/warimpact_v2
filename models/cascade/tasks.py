"""Celery tasks for Phase 4 Cascade / Cross-Stream Correlation."""

from __future__ import annotations

from typing import Any
from ingestion.common.celery_app import celery_app
from ingestion.common.logger import get_logger

logger = get_logger(__name__)


@celery_app.task(  # type: ignore[misc]
    name="models.cascade.tasks.run_cascade_analysis",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_cascade_analysis(self: Any, window_days: int = 7, k: float = 2.0) -> dict[str, Any]:
    """Celery task executing daily cascade contagion analysis."""
    import asyncio
    from models.cascade.worker import run_cascade_worker

    logger.info("celery_cascade_task_started", extra={"window_days": window_days, "k": k})
    rows_saved = asyncio.run(run_cascade_worker(window_days=window_days, k=k))

    return {
        "status": "success",
        "rows_saved": rows_saved,
        "window_days": window_days,
        "k": k,
    }
