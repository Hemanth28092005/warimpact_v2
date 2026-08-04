"""Celery tasks for India trade routes pipeline."""

from __future__ import annotations

from celery import shared_task  # type: ignore[import-untyped]
from models.trade_routes.routes import update_india_trade_routes


@shared_task(name="models.trade_routes.tasks.run_trade_routes_pipeline")
def run_trade_routes_pipeline() -> dict[str, Any]:
    """Daily scheduled task for trade route risk scoring."""
    return update_india_trade_routes()
