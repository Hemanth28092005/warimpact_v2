"""Celery tasks for geospatial event ingestion pipelines."""

from __future__ import annotations

import logging

from celery import shared_task  # type: ignore[import-untyped]

from ingestion.geo import flights, intel_seed, seismic

logger = logging.getLogger(__name__)


@shared_task(
    name="ingestion.geo.tasks.run_seismic_events",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=180,
)
def run_seismic_events() -> dict[str, int]:
    return seismic.run_seismic_sync()


@shared_task(
    name="ingestion.geo.tasks.run_military_flights",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=120,
)
def run_military_flights() -> dict[str, int]:
    return flights.run_flights_sync()


@shared_task(
    name="ingestion.geo.tasks.run_intel_seed",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=60,
)
def run_intel_seed() -> dict[str, int]:
    return intel_seed.run_intel_seed_sync()
