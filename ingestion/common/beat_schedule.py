"""Celery Beat schedule definitions.

Phase 0 intentionally registers no periodic jobs. Later phases must add
versioned schedules here instead of using cron or ad hoc sleep loops.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ingestion.common.config import get_settings

settings = get_settings()

BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "gdelt-run-latest-ingestion": {
        "task": "ingestion.gdelt.tasks.run_latest_ingestion",
        "schedule": timedelta(minutes=settings.gdelt_latest_interval_minutes),
    }
}
