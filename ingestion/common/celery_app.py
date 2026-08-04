"""Celery application configuration for ingestion and model automation."""

from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]

from ingestion.common.beat_schedule import BEAT_SCHEDULE
from ingestion.common.config import get_settings

settings = get_settings()

celery_app = Celery(
    "war_impact_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "ingestion.gdelt.tasks",
        "ingestion.dashboard.tasks",
        "models.sentiment.tasks",
        "models.cii.tasks",
        "models.aggression.tasks",
        "models.cascade.tasks",
        "models.chokepoints.tasks",
        "models.commodities.tasks",
        "models.trade_routes.tasks",
    ],
)

celery_app.conf.update(
    beat_schedule=BEAT_SCHEDULE,
    task_default_queue="default",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

app = celery_app


if __name__ == "__main__":
    celery_app.start()
