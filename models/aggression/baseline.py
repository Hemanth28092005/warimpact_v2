"""External baseline lookup interface for 0-event bilateral country pairs."""

from __future__ import annotations

from typing import Dict, Tuple

from models.aggression.cow_parser import COWBaselineRecord, build_cow_baseline_lookup


def get_external_baseline_lookup(seed_dir: str = "db/seed_data/cow") -> dict[tuple[str, str], COWBaselineRecord]:
    """Retrieve full Correlates of War (COW) baseline records for all 703 bilateral pairs."""
    return build_cow_baseline_lookup(seed_dir=seed_dir)
