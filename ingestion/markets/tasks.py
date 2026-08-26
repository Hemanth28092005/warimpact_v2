"""Celery tasks for market data ingestion pipelines."""

from __future__ import annotations

import logging

from celery import shared_task  # type: ignore[import-untyped]

from ingestion.markets import freight, prices, polymarket

logger = logging.getLogger(__name__)


@shared_task(
    name="ingestion.markets.tasks.run_commodity_prices",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=120,
)
def run_commodity_prices() -> dict[str, int]:
    return prices.run_commodity_prices_sync()


@shared_task(
    name="ingestion.markets.tasks.run_freight_indices",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=120,
)
def run_freight_indices() -> dict[str, int]:
    return freight.run_freight_sync()


@shared_task(
    name="ingestion.markets.tasks.run_prediction_markets",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=120,
)
def run_prediction_markets() -> dict[str, int]:
    return polymarket.run_prediction_markets_sync()
