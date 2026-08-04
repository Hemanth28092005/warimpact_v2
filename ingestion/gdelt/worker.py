"""Worker orchestration for the GDELT ingestion pipeline."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from psycopg import AsyncConnection

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from ingestion.common.source_health import SourceHealthEvent, record_source_health, utc_now
from ingestion.gdelt.cleaner import clean_events
from ingestion.gdelt.dispatcher import dispatch_events
from ingestion.gdelt.fetcher import GdeltFeedFile, download_export_csv, get_latest_feed_file, iter_backfill_feed_files
from ingestion.gdelt.parser import parse_gdelt_csv

logger = get_logger(__name__)


@dataclass(frozen=True)
class IngestionRunSummary:
    run_id: UUID
    mode: str
    feeds_processed: int
    records_processed: int
    records_failed: int


async def run_ingestion(
    mode: str,
    start: datetime | None = None,
    end: datetime | None = None,
    run_id: UUID | None = None,
    celery_task_id: str | None = None,
) -> IngestionRunSummary:
    run_id = run_id or uuid4()
    started_at = utc_now()
    logger.info("gdelt_ingestion_started", extra={"mode": mode, "run_id": run_id})

    async with open_async_connection() as conn:
        try:
            if mode == "latest":
                feed_files = [await get_latest_feed_file(conn, run_id, celery_task_id)]
            elif mode == "backfill":
                if start is None or end is None:
                    raise ValueError("backfill mode requires start and end")
                feed_files = list(iter_backfill_feed_files(start, end))
            else:
                raise ValueError(f"unsupported mode: {mode}")

            records_processed = 0
            records_failed = 0
            for feed_file in feed_files:
                try:
                    processed, failed = await _process_feed_file(conn, feed_file, run_id, celery_task_id)
                    records_processed += processed
                    records_failed += failed
                except Exception as exc:
                    records_failed += 1
                    logger.warning(
                        "gdelt_feed_file_skipped",
                        extra={"url": feed_file.url, "error": str(exc)},
                    )

            await record_source_health(
                conn,
                SourceHealthEvent(
                    source_name="gdelt",
                    feed_name=f"{mode}_run",
                    status="succeeded",
                    records_processed=records_processed,
                    records_failed=records_failed,
                    error_message=None,
                    fetch_started_at=started_at,
                    fetch_completed_at=utc_now(),
                    run_id=run_id,
                    celery_task_id=celery_task_id,
                ),
            )
            await conn.commit()
        except Exception as exc:
            await record_source_health(
                conn,
                SourceHealthEvent(
                    source_name="gdelt",
                    feed_name=f"{mode}_run",
                    status="failed",
                    records_processed=0,
                    records_failed=1,
                    error_message=str(exc),
                    fetch_started_at=started_at,
                    fetch_completed_at=utc_now(),
                    run_id=run_id,
                    celery_task_id=celery_task_id,
                ),
            )
            await conn.commit()
            logger.exception("gdelt_ingestion_failed", extra={"mode": mode, "run_id": run_id})
            raise

    summary = IngestionRunSummary(
        run_id=run_id,
        mode=mode,
        feeds_processed=len(feed_files),
        records_processed=records_processed,
        records_failed=records_failed,
    )
    logger.info("gdelt_ingestion_completed", extra=summary.__dict__)
    return summary


async def _process_feed_file(
    conn: AsyncConnection,
    feed_file: GdeltFeedFile,
    run_id: UUID,
    celery_task_id: str | None,
) -> tuple[int, int]:
    csv_text = await download_export_csv(conn, feed_file, run_id, celery_task_id)
    parsed_events, parse_failures = parse_gdelt_csv(csv_text)
    cleaned_events, clean_failures = clean_events(parsed_events)
    inserted = await dispatch_events(conn, cleaned_events)
    await record_source_health(
        conn,
        SourceHealthEvent(
            source_name="gdelt",
            feed_name=feed_file.url.rsplit("/", 1)[-1],
            status="processed",
            records_processed=inserted,
            records_failed=parse_failures + clean_failures,
            error_message=None,
            fetch_started_at=utc_now(),
            fetch_completed_at=utc_now(),
            run_id=run_id,
            celery_task_id=celery_task_id,
        ),
    )
    await conn.commit()
    return inserted, parse_failures + clean_failures


def run_ingestion_sync(
    mode: str,
    start: datetime | None = None,
    end: datetime | None = None,
    celery_task_id: str | None = None,
) -> dict[str, object]:
    summary = asyncio.run(
        run_ingestion(mode=mode, start=start, end=end, celery_task_id=celery_task_id)
    )
    return {
        "run_id": str(summary.run_id),
        "mode": summary.mode,
        "feeds_processed": summary.feeds_processed,
        "records_processed": summary.records_processed,
        "records_failed": summary.records_failed,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GDELT ingestion pipeline")
    parser.add_argument("--mode", choices=["latest", "backfill"], required=True)
    parser.add_argument("--start", help="Backfill start timestamp, ISO format")
    parser.add_argument("--end", help="Backfill end timestamp, ISO format")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    start = datetime.fromisoformat(args.start) if args.start else None
    end = datetime.fromisoformat(args.end) if args.end else None
    print(run_ingestion_sync(mode=args.mode, start=start, end=end))


if __name__ == "__main__":
    main()
