"""Unit tests for Correlates of War (COW) dataset parser module."""

from __future__ import annotations

import os
import pytest

from models.aggression.cow_parser import (
    build_cow_baseline_lookup,
    load_cow_state_code_map,
    parse_cow_alliances,
    parse_cow_mids,
    TARGET_COUNTRIES,
)


def test_cow_state_code_map_loads() -> None:
    seed_dir = "db/seed_data/cow"
    if not os.path.exists(os.path.join(seed_dir, "states2016.csv")):
        pytest.skip("states2016.csv seed file not present")

    ccode_map = load_cow_state_code_map(seed_dir)
    assert ccode_map.get("2") == "USA"
    assert ccode_map.get("200") == "GBR"
    assert ccode_map.get("365") == "RUS"
    assert ccode_map.get("710") == "CHN"


def test_cow_parser_mids_and_alliances_conversion_rules() -> None:
    seed_dir = "db/seed_data/cow"
    if not os.path.exists(os.path.join(seed_dir, "states2016.csv")):
        pytest.skip("COW seed data files not present")

    ccode_map = load_cow_state_code_map(seed_dir)
    alliances = parse_cow_alliances(seed_dir, ccode_map)
    mids = parse_cow_mids(seed_dir, ccode_map)

    # 1. Verify alliance scores are bounded in [10.0, 30.0]
    for pair, (score, cit, yr, rank) in alliances.items():
        assert 10.0 <= score <= 30.0
        assert yr == 2012

    # 2. Verify MID scores are bounded in [50.0, 95.0]
    for pair, (score, cit, yr) in mids.items():
        assert 50.0 <= score <= 95.0
        assert yr == 2010


def test_cow_baseline_lookup_full_coverage_and_unscored_handling() -> None:
    seed_dir = "db/seed_data/cow"
    if not os.path.exists(os.path.join(seed_dir, "states2016.csv")):
        pytest.skip("COW seed data files not present")

    lookup = build_cow_baseline_lookup(seed_dir)
    total_expected_pairs = (len(TARGET_COUNTRIES) * (len(TARGET_COUNTRIES) - 1)) // 2
    assert len(lookup) == total_expected_pairs  # 703 pairs

    # Verify every pair is canonically ordered
    for (c_a, c_b), rec in lookup.items():
        assert c_a < c_b
        assert rec.country_a == c_a
        assert rec.country_b == c_b

        # Unscored pairs must have NULL aggression_score and NULL baseline_data_year
        if rec.aggression_score is None:
            assert rec.baseline_source is None
            assert rec.baseline_data_year is None
            assert rec.data_source == "external_baseline"
        else:
            assert 0.0 <= rec.aggression_score <= 100.0
            assert rec.baseline_data_year in (2010, 2012)
