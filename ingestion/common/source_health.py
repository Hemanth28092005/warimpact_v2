"""Persistence helpers for source health records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from psycopg import AsyncConnection


@dataclass(frozen=True)
class SourceHealthEvent:
    source_name: str
    feed_name: str
    status: str
    records_processed: int
    records_failed: int
    error_message: str | None
    fetch_started_at: datetime
    fetch_completed_at: datetime | None
    run_id: UUID
    celery_task_id: str | None = None


async def record_source_health(conn: AsyncConnection, event: SourceHealthEvent) -> None:
    await conn.execute(
        """
        insert into source_health (
            source_name, feed_name, status, records_processed, records_failed,
            error_message, fetch_started_at, fetch_completed_at, run_id, celery_task_id
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event.source_name,
            event.feed_name,
            event.status,
            event.records_processed,
            event.records_failed,
            event.error_message,
            event.fetch_started_at,
            event.fetch_completed_at,
            event.run_id,
            event.celery_task_id,
        ),
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    print("source_health helper ready")
