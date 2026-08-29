"""Celery Beat schedule definitions.

Phase 0 intentionally registers no periodic jobs. Later phases must add
versioned schedules here instead of using cron or ad hoc sleep loops.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from celery.schedules import crontab  # type: ignore[import-untyped]

from ingestion.common.config import get_settings

settings = get_settings()

BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "gdelt-run-latest-ingestion": {
        "task": "ingestion.gdelt.tasks.run_latest_ingestion",
        "schedule": timedelta(minutes=settings.gdelt_latest_interval_minutes),
    },
    "models-run-daily-sentiment-pipeline": {
        "task": "models.sentiment.tasks.run_daily_sentiment_pipeline",
        "schedule": timedelta(hours=24),
    },
    "models-run-daily-cii-pipeline": {
        "task": "models.cii.tasks.run_daily_cii_pipeline",
        "schedule": timedelta(hours=24),
    },
    "models-run-daily-aggression-pipeline": {
        "task": "models.aggression.tasks.run_daily_aggression_pipeline",
        "schedule": timedelta(hours=24),
    },
    "models-retrain-cii-monthly": {
        "task": "models.cii.tasks.retrain_cii_monthly",
        "schedule": crontab(day_of_month="1", hour="3", minute="0"),
    },
    "models-fetch-escalation-articles": {
        "task": "models.sentiment.tasks.fetch_escalation_articles",
        "schedule": timedelta(minutes=settings.gdelt_latest_interval_minutes),
    },
    "models-run-daily-cascade-pipeline": {
        "task": "models.cascade.tasks.run_cascade_analysis",
        "schedule": crontab(hour="2", minute="30"),
    },
    "ingestion-run-regional-headlines": {
        "task": "ingestion.dashboard.tasks.run_regional_headlines",
        "schedule": timedelta(minutes=15),
    },
    "ingestion-run-government-actions": {
        "task": "ingestion.dashboard.tasks.run_government_actions",
        "schedule": timedelta(minutes=15),
    },
    "ingestion-run-protests": {
        "task": "ingestion.dashboard.tasks.run_protests",
        "schedule": timedelta(minutes=10),
    },
    "models-run-chokepoint-disruption": {
        "task": "models.chokepoints.tasks.run_chokepoint_disruption_pipeline",
        "schedule": timedelta(minutes=15),
    },
    "models-run-commodity-news": {
        "task": "models.commodities.tasks.run_commodity_news_pipeline",
        "schedule": timedelta(minutes=15),
    },
    "models-run-trade-routes-pipeline": {
        "task": "models.trade_routes.tasks.run_trade_routes_pipeline",
        "schedule": timedelta(hours=24),
    },
    "ingestion-run-commodity-prices": {
        "task": "ingestion.markets.tasks.run_commodity_prices",
        "schedule": timedelta(minutes=30),
    },
    "ingestion-run-freight-indices": {
        "task": "ingestion.markets.tasks.run_freight_indices",
        "schedule": timedelta(hours=12),
    },
    "ingestion-run-seismic-events": {
        "task": "ingestion.geo.tasks.run_seismic_events",
        "schedule": timedelta(minutes=15),
    },
    "ingestion-run-military-flights": {
        "task": "ingestion.geo.tasks.run_military_flights",
        "schedule": timedelta(minutes=5),
    },
    "ingestion-run-intel-seed": {
        "task": "ingestion.geo.tasks.run_intel_seed",
        "schedule": crontab(hour="4", minute="0"),
    },
    "ingestion-run-prediction-markets": {
        "task": "ingestion.markets.tasks.run_prediction_markets",
        "schedule": timedelta(hours=1),
    },
    "ingestion-run-naval-fleets": {
        "task": "ingestion.geo.tasks.run_naval_fleets",
        "schedule": timedelta(minutes=30),
    },
}
