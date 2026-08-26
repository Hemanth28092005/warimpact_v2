"""Celery application configuration for ingestion and model automation."""

import sys
import asyncio
from celery import Celery  # type: ignore[import-untyped]

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
        "ingestion.geo.tasks",
        "ingestion.markets.tasks",
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
