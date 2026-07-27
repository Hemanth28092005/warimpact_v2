"""Celery Beat schedule definitions.

Phase 0 intentionally registers no periodic jobs. Later phases must add
versioned schedules here instead of using cron or ad hoc sleep loops.
"""

from __future__ import annotations

from typing import Any

BEAT_SCHEDULE: dict[str, dict[str, Any]] = {}
