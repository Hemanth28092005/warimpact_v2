"""Fetcher for GDELT 2.0 Event Database CSV ZIP files."""

from __future__ import annotations

import zipfile
import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from uuid import UUID

import httpx
from psycopg import AsyncConnection

from ingestion.common.config import get_settings
from ingestion.common.logger import get_logger
from ingestion.common.source_health import SourceHealthEvent, record_source_health, utc_now

logger = get_logger(__name__)

GDELT_BASE_URL = "https://data.gdeltproject.org/gdeltv2"
FETCH_RETRY_DELAYS_SECONDS = (1, 2, 4)


@dataclass(frozen=True)
class GdeltFeedFile:
    url: str
    timestamp: datetime | None


def parse_lastupdate(text: str) -> GdeltFeedFile:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        url = parts[2]
        if url.endswith(".export.CSV.zip"):
            return GdeltFeedFile(url=url, timestamp=_timestamp_from_url(url))
    raise ValueError("lastupdate.txt did not contain an export CSV ZIP URL")


async def get_latest_feed_file(conn: AsyncConnection, run_id: UUID, celery_task_id: str | None) -> GdeltFeedFile:
    settings = get_settings()
    text = await _fetch_text_with_health(
        conn=conn,
        url=settings.gdelt_lastupdate_url,
        feed_name="lastupdate",
        run_id=run_id,
        celery_task_id=celery_task_id,
    )
    return parse_lastupdate(text)


async def download_export_csv(
    conn: AsyncConnection,
    feed_file: GdeltFeedFile,
    run_id: UUID,
    celery_task_id: str | None,
) -> str:
    content = await _fetch_bytes_with_health(
        conn=conn,
        url=feed_file.url,
        feed_name=feed_file.url.rsplit("/", 1)[-1],
        run_id=run_id,
        celery_task_id=celery_task_id,
    )
    with zipfile.ZipFile(BytesIO(content)) as archive:
        names = archive.namelist()
        if not names:
            raise ValueError(f"{feed_file.url} contained no files")
        with archive.open(names[0]) as csv_file:
            return csv_file.read().decode("utf-8", errors="replace")


def iter_backfill_feed_files(start: datetime, end: datetime) -> Iterable[GdeltFeedFile]:
    current = _floor_to_15_minutes(start)
    while current <= end:
        stamp = current.strftime("%Y%m%d%H%M%S")
        yield GdeltFeedFile(url=f"{GDELT_BASE_URL}/{stamp}.export.CSV.zip", timestamp=current)
        current += timedelta(minutes=15)


async def _fetch_text_with_health(
    conn: AsyncConnection,
    url: str,
    feed_name: str,
    run_id: UUID,
    celery_task_id: str | None,
) -> str:
    content = await _fetch_with_health(conn, url, feed_name, run_id, celery_task_id)
    return content.decode("utf-8")


async def _fetch_bytes_with_health(
    conn: AsyncConnection,
    url: str,
    feed_name: str,
    run_id: UUID,
    celery_task_id: str | None,
) -> bytes:
    return await _fetch_with_health(conn, url, feed_name, run_id, celery_task_id)


async def _fetch_with_health(
    conn: AsyncConnection,
    url: str,
    feed_name: str,
    run_id: UUID,
    celery_task_id: str | None,
) -> bytes:
    started_at = utc_now()

    last_error: Exception | None = None
    for attempt in range(1, len(FETCH_RETRY_DELAYS_SECONDS) + 2):
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                content = response.content
        except Exception as exc:
            last_error = exc
            await record_source_health(
                conn,
                SourceHealthEvent(
                    source_name="gdelt",
                    feed_name=feed_name,
                    status="fetch_attempt_failed",
                    records_processed=0,
                    records_failed=1,
                    error_message=f"attempt {attempt}: {exc}",
                    fetch_started_at=started_at,
                    fetch_completed_at=utc_now(),
                    run_id=run_id,
                    celery_task_id=celery_task_id,
                ),
            )
            await conn.commit()
            if attempt <= len(FETCH_RETRY_DELAYS_SECONDS):
                await asyncio.sleep(FETCH_RETRY_DELAYS_SECONDS[attempt - 1])
                continue
            break

        await record_source_health(
            conn,
            SourceHealthEvent(
                source_name="gdelt",
                feed_name=feed_name,
                status="fetch_succeeded",
                records_processed=0,
                records_failed=0,
                error_message=f"attempt {attempt}",
                fetch_started_at=started_at,
                fetch_completed_at=utc_now(),
                run_id=run_id,
                celery_task_id=celery_task_id,
            ),
        )
        await conn.commit()
        logger.info("gdelt_fetch_succeeded", extra={"feed_name": feed_name, "run_id": run_id})
        return content

    if last_error is not None:
        await record_source_health(
            conn,
            SourceHealthEvent(
                source_name="gdelt",
                feed_name=feed_name,
                status="fetch_failed",
                records_processed=0,
                records_failed=1,
                error_message=str(last_error),
                fetch_started_at=started_at,
                fetch_completed_at=utc_now(),
                run_id=run_id,
                celery_task_id=celery_task_id,
            ),
        )
        await conn.commit()
        raise last_error

    raise RuntimeError("fetch failed without an exception")


def _timestamp_from_url(url: str) -> datetime | None:
    filename = url.rsplit("/", 1)[-1]
    stamp = filename.split(".", 1)[0]
    if len(stamp) != 14:
        return None
    return datetime.strptime(stamp, "%Y%m%d%H%M%S")


def _floor_to_15_minutes(value: datetime) -> datetime:
    return value.replace(minute=(value.minute // 15) * 15, second=0, microsecond=0)


if __name__ == "__main__":
    print("GDELT fetcher ready")
