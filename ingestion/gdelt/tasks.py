"""Celery task wrappers for the GDELT ingestion worker."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ingestion.common.celery_app import celery_app
from ingestion.gdelt.worker import run_ingestion_sync


@celery_app.task(  # type: ignore[misc]
    name="ingestion.gdelt.tasks.run_latest_ingestion",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_latest_ingestion(self: Any) -> dict[str, object]:
    return run_ingestion_sync(mode="latest", celery_task_id=self.request.id)


@celery_app.task(  # type: ignore[misc]
    name="ingestion.gdelt.tasks.run_backfill_ingestion",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_backfill_ingestion(self: Any, start: str, end: str) -> dict[str, object]:
    return run_ingestion_sync(
        mode="backfill",
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat(end),
        celery_task_id=self.request.id,
    )


if __name__ == "__main__":
    print("GDELT Celery tasks ready")
