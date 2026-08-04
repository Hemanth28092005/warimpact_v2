"""Celery tasks for maritime chokepoints disruption engine."""

from __future__ import annotations

from celery import shared_task  # type: ignore[import-untyped]
from models.chokepoints.disruption import calculate_chokepoint_disruptions


@shared_task(name="models.chokepoints.tasks.run_chokepoint_disruption_pipeline")
def run_chokepoint_disruption_pipeline() -> dict[str, int]:
    """15-min scheduled task for maritime chokepoint disruption scoring."""
    return calculate_chokepoint_disruptions()
