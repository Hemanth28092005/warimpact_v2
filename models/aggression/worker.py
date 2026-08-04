"""Worker orchestration for Country Bilateral Aggression Score pipeline."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.aggression.baseline import get_external_baseline_lookup
from models.aggression.cow_parser import generate_all_canonical_pairs, TARGET_COUNTRIES
from models.aggression.pairs import extract_trailing_365d_bilateral_events
from models.aggression.scorer import compute_pair_aggression_score

logger = get_logger(__name__)


@dataclass(frozen=True)
class AggressionRunSummary:
    target_date: date
    total_canonical_pairs: int
    gdelt_derived_pairs_count: int
    external_baseline_pairs_count: int
    explicitly_unscored_pairs_count: int
    total_trailing_365d_events: int
    skipped_null_actor_events: int
    computed_at: datetime


async def run_aggression_pipeline(
    target_date: date | None = None,
    seed_dir: str = "db/seed_data/cow",
) -> AggressionRunSummary:
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    logger.info("aggression_pipeline_started", extra={"target_date": str(target_date)})
    computed_at = datetime.now(timezone.utc)

    # 1. Load COW baseline lookup table for all 703 pairs
    cow_baseline_map = get_external_baseline_lookup(seed_dir=seed_dir)
    all_703_pairs = generate_all_canonical_pairs(TARGET_COUNTRIES)

    async with open_async_connection() as conn:
        # 2. Extract trailing 365 days of bilateral GDELT events
        events_by_pair, last_event_dates, pair_summary = await extract_trailing_365d_bilateral_events(
            conn=conn,
            target_date=target_date,
            lookback_days=365,
        )

        gdelt_derived_count = 0
        external_baseline_count = 0
        unscored_count = 0

        # 3. Upsert records for all 703 canonical pairs
        async with conn.cursor() as cur:
            for pair in all_703_pairs:
                c_a, c_b = pair
                last_date = last_event_dates.get(pair)

                if pair in events_by_pair and len(events_by_pair[pair]) > 0:
                    pair_events = events_by_pair[pair]
                    score = compute_pair_aggression_score(pair_events)
                    event_cnt = len(pair_events)
                    data_src = "gdelt_derived"
                    base_src = None
                    base_yr = None
                    gdelt_derived_count += 1
                else:
                    cow_rec = cow_baseline_map.get(pair)
                    if cow_rec and cow_rec.aggression_score is not None:
                        score = cow_rec.aggression_score
                        event_cnt = 0
                        data_src = "external_baseline"
                        base_src = cow_rec.baseline_source
                        base_yr = cow_rec.baseline_data_year
                        external_baseline_count += 1
                    else:
                        score = None
                        event_cnt = 0
                        data_src = "external_baseline"
                        base_src = None
                        base_yr = None
                        unscored_count += 1

                score_decimal = Decimal(str(score)) if score is not None else None

                await cur.execute(
                    """
                    INSERT INTO country_aggression_scores (
                        country_a, country_b, aggression_score, event_count,
                        data_source, baseline_source, baseline_data_year,
                        last_event_date, computed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (country_a, country_b) DO UPDATE SET
                        aggression_score = EXCLUDED.aggression_score,
                        event_count = EXCLUDED.event_count,
                        data_source = EXCLUDED.data_source,
                        baseline_source = EXCLUDED.baseline_source,
                        baseline_data_year = EXCLUDED.baseline_data_year,
                        last_event_date = EXCLUDED.last_event_date,
                        computed_at = EXCLUDED.computed_at
                    """,
                    (
                        c_a,
                        c_b,
                        score_decimal,
                        event_cnt,
                        data_src,
                        base_src,
                        base_yr,
                        last_date,
                        computed_at,
                    ),
                )
        await conn.commit()

    summary = AggressionRunSummary(
        target_date=target_date,
        total_canonical_pairs=len(all_703_pairs),
        gdelt_derived_pairs_count=gdelt_derived_count,
        external_baseline_pairs_count=external_baseline_count,
        explicitly_unscored_pairs_count=unscored_count,
        total_trailing_365d_events=pair_summary.bilateral_events_extracted,
        skipped_null_actor_events=pair_summary.skipped_null_actor_events,
        computed_at=computed_at,
    )

    logger.info("aggression_pipeline_completed", extra=summary.__dict__)
    return summary


def run_aggression_pipeline_sync(
    target_date: date | None = None,
    seed_dir: str = "db/seed_data/cow",
) -> dict[str, Any]:
    summary = asyncio.run(run_aggression_pipeline(target_date=target_date, seed_dir=seed_dir))
    return {
        "target_date": str(summary.target_date),
        "total_canonical_pairs": summary.total_canonical_pairs,
        "gdelt_derived_pairs_count": summary.gdelt_derived_pairs_count,
        "external_baseline_pairs_count": summary.external_baseline_pairs_count,
        "explicitly_unscored_pairs_count": summary.explicitly_unscored_pairs_count,
        "total_trailing_365d_events": summary.total_trailing_365d_events,
        "skipped_null_actor_events": summary.skipped_null_actor_events,
        "computed_at": summary.computed_at.isoformat(),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Bilateral Aggression Score pipeline")
    parser.add_argument("--date", help="Target computation date, ISO format (YYYY-MM-DD)")
    parser.add_argument("--seed-dir", default="db/seed_data/cow", help="Path to COW seed data directory")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    target_date = date.fromisoformat(args.date) if args.date else None
    res = run_aggression_pipeline_sync(target_date=target_date, seed_dir=args.seed_dir)
    print("=== BILATERAL AGGRESSION PIPELINE COMPLETED ===")
    for k, v in res.items():
        print(f"  {k:<32}: {v}")


if __name__ == "__main__":
    main()
