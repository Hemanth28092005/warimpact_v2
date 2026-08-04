"""Worker orchestration for Phase 3 Country Instability Index (CII) pipeline."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.cii.inference import score_country_instability

logger = get_logger(__name__)


@dataclass(frozen=True)
class CIIRunSummary:
    target_date: date
    countries_scored_count: int
    model_version: str


async def run_cii_pipeline(
    target_date: date | None = None,
) -> CIIRunSummary:
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    logger.info("cii_pipeline_started", extra={"target_date": str(target_date)})

    async with open_async_connection() as conn:
        predictions = await score_country_instability(conn, target_date)

    model_ver = predictions[0].model_version if predictions else "unknown"

    summary = CIIRunSummary(
        target_date=target_date,
        countries_scored_count=len(predictions),
        model_version=model_ver,
    )
    logger.info("cii_pipeline_completed", extra=summary.__dict__)
    return summary


def run_cii_pipeline_sync(
    target_date: date | None = None,
) -> dict[str, Any]:
    summary = asyncio.run(run_cii_pipeline(target_date=target_date))
    return {
        "target_date": str(summary.target_date),
        "countries_scored_count": summary.countries_scored_count,
        "model_version": summary.model_version,
    }


async def retrain_cii_pipeline(
    target_end_date: date | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    from models.cii.train import run_training_pipeline

    metadata, guardrail = await run_training_pipeline(
        target_end_date=target_end_date,
        model_version=model_version,
    )
    return {
        "model_version": metadata.model_version,
        "status": guardrail.status,
        "is_promoted": guardrail.is_promoted,
        "reason": guardrail.reason,
        "val_r2": metadata.regressor.val_r2,
        "val_roc_auc": metadata.classifier.val_roc_auc,
    }


def retrain_cii_pipeline_sync(
    target_end_date: date | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    return asyncio.run(retrain_cii_pipeline(target_end_date=target_end_date, model_version=model_version))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 3 Country Instability Index pipeline")
    parser.add_argument("--date", help="Target score date, ISO format (YYYY-MM-DD)")
    parser.add_argument("--retrain", action="store_true", help="Execute monthly retraining pipeline")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.retrain:
        print(retrain_cii_pipeline_sync())
    else:
        target_date = date.fromisoformat(args.date) if args.date else None
        print(run_cii_pipeline_sync(target_date=target_date))


if __name__ == "__main__":
    main()
