"""Celery application configuration for ingestion and model automation."""

from __future__ import annotations

import os

from celery import Celery  # type: ignore[import-untyped]
from dotenv import load_dotenv

from ingestion.common.beat_schedule import BEAT_SCHEDULE

load_dotenv()

DEFAULT_BROKER_URL = "redis://localhost:6379/0"
DEFAULT_RESULT_BACKEND = "redis://localhost:6379/1"

celery_app = Celery(
    "war_impact_platform",
    broker=os.getenv("CELERY_BROKER_URL", DEFAULT_BROKER_URL),
    backend=os.getenv("CELERY_RESULT_BACKEND", DEFAULT_RESULT_BACKEND),
    include=[],
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
