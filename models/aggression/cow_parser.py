"""Programmatic parser for Correlates of War (COW) Formal Alliances (v4.1) and MID (v4.2/5.0) datasets."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ingestion.common.logger import get_logger

logger = get_logger(__name__)

# List of 38 target in-scope ISO-3 country codes from SCOPE.md
TARGET_COUNTRIES: list[str] = [
    "USA", "GBR", "FRA", "CHN", "RUS",
    "IND", "DEU", "JPN", "BRA", "CAN", "ITA", "KOR", "MEX", "AUS", "TUR", "SAU", "ZAF", "IDN", "ARG",
    "ISR", "NIC", "PAK", "ASM", "GMB", "ESP", "MUS", "BOL", "GTM", "SSD",
    "SYR", "YEM", "MMR", "SDN", "SOM", "LBY", "AFG", "UKR", "HTI"
]

ALLIANCE_SSMTYPE_MAP: dict[str, tuple[float, str]] = {
    "Type I: Defense Pact": (10.0, "Correlates of War Project — Formal Alliances v4.1 (Defense Pact)"),
    "Type II: Neutrality": (20.0, "Correlates of War Project — Formal Alliances v4.1 (Neutrality Pact)"),
    "Type IIa: Non-Aggression Pact": (25.0, "Correlates of War Project — Formal Alliances v4.1 (Non-Aggression Pact)"),
    "Type IIb: Non-Aggression Pact": (25.0, "Correlates of War Project — Formal Alliances v4.1 (Non-Aggression Pact)"),
    "Type III: Entente": (30.0, "Correlates of War Project — Formal Alliances v4.1 (Entente)"),
}

MID_HOSTLEV_MAP: dict[str, tuple[float, str]] = {
    "5": (95.0, "Correlates of War Project — MID v4.2 (War)"),
    "4": (80.0, "Correlates of War Project — MID v4.2 (Use of Force)"),
    "3": (65.0, "Correlates of War Project — MID v4.2 (Display of Force)"),
    "2": (50.0, "Correlates of War Project — MID v4.2 (Threat to Use Force)"),
}


@dataclass(frozen=True)
class COWBaselineRecord:
    country_a: str
    country_b: str
    aggression_score: Optional[float]
    data_source: str
    baseline_source: Optional[str]
    baseline_data_year: Optional[int]


COW_ABB_TO_ISO3: dict[str, str] = {
    "UKG": "GBR",
    "FRN": "FRA",
    "GMY": "DEU",
    "SAF": "ZAF",
    "ROK": "KOR",
    "MYA": "MMR",
    "BUR": "MMR",
    "INS": "IDN",
    "AUL": "AUS",
    "SUD": "SDN",
    "SPN": "ESP",
    "MAS": "MUS",
}


def load_cow_state_code_map(seed_dir: str) -> dict[str, str]:
    """Load COW numeric state code (ccode) -> ISO-3 string mapping from states2016.csv."""
    filepath = os.path.join(seed_dir, "states2016.csv")
    ccode_map: dict[str, str] = {}
    if not os.path.exists(filepath):
        logger.warning("cow_states_file_not_found", extra={"filepath": filepath})
        return ccode_map

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ccode = row.get("ccode", "").strip()
            stateabb = row.get("stateabb", "").strip()
            if ccode and stateabb:
                iso3 = COW_ABB_TO_ISO3.get(stateabb, stateabb)
                ccode_map[ccode] = iso3
    return ccode_map


def generate_all_canonical_pairs(target_countries: list[str]) -> list[tuple[str, str]]:
    """Generate all C(N, 2) unique pairs in canonical country_a < country_b order."""
    sorted_countries = sorted(list(set(target_countries)))
    pairs: list[tuple[str, str]] = []
    for i in range(len(sorted_countries)):
        for j in range(i + 1, len(sorted_countries)):
            pairs.append((sorted_countries[i], sorted_countries[j]))
    return pairs


def parse_cow_alliances(seed_dir: str, ccode_map: dict[str, str]) -> dict[tuple[str, str], tuple[float, str, int, int]]:
    """Parse alliance_v4.1_by_member.csv, group by version4id, deduplicate co-members, generate C(N,2) pairs.

    Returns dict mapping (country_a, country_b) -> (score, citation, baseline_data_year, ssmtype_rank).
    """
    filepath = os.path.join(seed_dir, "alliance_v4.1_by_member.csv")
    if not os.path.exists(filepath):
        logger.warning("cow_alliances_file_not_found", extra={"filepath": filepath})
        return {}

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Group by version4id
    by_vid: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        vid = r.get("version4id")
        if vid:
            by_vid.setdefault(vid, []).append(r)

    alliance_pairs: dict[tuple[str, str], tuple[float, str, int, int]] = {}

    for vid, v_rows in by_vid.items():
        if not v_rows:
            continue
        ss_type_str = v_rows[0].get("ss_type", "").strip()
        if ss_type_str not in ALLIANCE_SSMTYPE_MAP:
            continue
        score, citation = ALLIANCE_SSMTYPE_MAP[ss_type_str]

        # Extract unique ISO-3 country codes for in-scope target countries in this alliance
        in_scope_members: set[str] = set()
        max_end_year = 0
        is_active = False

        for r in v_rows:
            ccode = r.get("ccode", "").strip()
            iso3 = ccode_map.get(ccode)
            if iso3 and iso3 in TARGET_COUNTRIES:
                in_scope_members.add(iso3)

            ey = r.get("all_end_year", "").strip()
            if not ey or ey == "-9":
                is_active = True
            else:
                try:
                    max_end_year = max(max_end_year, int(ey))
                except ValueError:
                    pass

        effective_end_year = 2012 if is_active else max_end_year
        rank_ssmtype = int(score)  # Lower is stronger (e.g. 10 < 20 < 25 < 30)

        # Generate C(N, 2) unique pairs for co-members
        member_list = sorted(list(in_scope_members))
        for i in range(len(member_list)):
            for j in range(i + 1, len(member_list)):
                c_a, c_b = member_list[i], member_list[j]
                pair = (c_a, c_b)

                # Tie-breaking rule: active/most recent end_year, then lowest ssmtype
                if pair not in alliance_pairs:
                    alliance_pairs[pair] = (score, citation, 2012, rank_ssmtype)
                else:
                    existing_score, existing_cit, existing_year, existing_rank = alliance_pairs[pair]
                    if effective_end_year > existing_year or (effective_end_year == existing_year and rank_ssmtype < existing_rank):
                        alliance_pairs[pair] = (score, citation, 2012, rank_ssmtype)

    return alliance_pairs


def parse_cow_mids(seed_dir: str, ccode_map: dict[str, str]) -> dict[tuple[str, str], tuple[float, str, int]]:
    """Parse MIDB_4.2.csv (or MIDA_4.2.csv) and extract dyadic hostility level records.

    Returns dict mapping (country_a, country_b) -> (score, citation, baseline_data_year).
    """
    filepath = os.path.join(seed_dir, "MIDB_4.2.csv")
    if not os.path.exists(filepath):
        filepath = os.path.join(seed_dir, "MIDA_4.2.csv")

    if not os.path.exists(filepath):
        logger.warning("cow_mids_file_not_found", extra={"filepath": filepath})
        return {}

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Group by dispnum3 (Dispute Number)
    by_disp: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        disp = r.get("dispnum3") or r.get("dispnum")
        if disp:
            by_disp.setdefault(disp, []).append(r)

    mid_pairs: dict[tuple[str, str], tuple[float, str, int]] = {}

    for disp, d_rows in by_disp.items():
        if not d_rows:
            continue
        
        # Get highest hostility level in dispute
        max_hostlev = 0
        for r in d_rows:
            hl = r.get("hostlev", "").strip()
            if hl.isdigit():
                max_hostlev = max(max_hostlev, int(hl))

        hostlev_str = str(max_hostlev)
        if hostlev_str not in MID_HOSTLEV_MAP:
            continue

        score, citation = MID_HOSTLEV_MAP[hostlev_str]

        # Extract target country participants
        participants: set[str] = set()
        for r in d_rows:
            ccode = r.get("ccode", "").strip()
            iso3 = ccode_map.get(ccode) or r.get("stabb", "").strip()
            if iso3 and iso3 in TARGET_COUNTRIES:
                participants.add(iso3)

        part_list = sorted(list(participants))
        for i in range(len(part_list)):
            for j in range(i + 1, len(part_list)):
                c_a, c_b = part_list[i], part_list[j]
                pair = (c_a, c_b)

                if pair not in mid_pairs:
                    mid_pairs[pair] = (score, citation, 2010)
                else:
                    existing_score = mid_pairs[pair][0]
                    if score > existing_score:
                        mid_pairs[pair] = (score, citation, 2010)

    return mid_pairs


def build_cow_baseline_lookup(seed_dir: str = "db/seed_data/cow") -> dict[tuple[str, str], COWBaselineRecord]:
    """Combine COW Alliances and MIDs into full baseline lookup table for all 703 pairs."""
    ccode_map = load_cow_state_code_map(seed_dir)
    alliance_map = parse_cow_alliances(seed_dir, ccode_map)
    mid_map = parse_cow_mids(seed_dir, ccode_map)

    all_pairs = generate_all_canonical_pairs(TARGET_COUNTRIES)
    baseline_records: dict[tuple[str, str], COWBaselineRecord] = {}

    unscored_count = 0
    mid_count = 0
    alliance_count = 0

    for pair in all_pairs:
        c_a, c_b = pair

        # MID Precedence: any MID conflict record (hostlev >= 2) overrides Alliance paper record
        if pair in mid_map:
            score, citation, year = mid_map[pair]
            baseline_records[pair] = COWBaselineRecord(
                country_a=c_a,
                country_b=c_b,
                aggression_score=score,
                data_source="external_baseline",
                baseline_source=citation,
                baseline_data_year=year,
            )
            mid_count += 1
        elif pair in alliance_map:
            score, citation, year, _ = alliance_map[pair]
            baseline_records[pair] = COWBaselineRecord(
                country_a=c_a,
                country_b=c_b,
                aggression_score=score,
                data_source="external_baseline",
                baseline_source=citation,
                baseline_data_year=year,
            )
            alliance_count += 1
        else:
            # Explicitly unscored pair
            baseline_records[pair] = COWBaselineRecord(
                country_a=c_a,
                country_b=c_b,
                aggression_score=None,
                data_source="external_baseline",
                baseline_source=None,
                baseline_data_year=None,
            )
            unscored_count += 1

    logger.info(
        "cow_baseline_lookup_built",
        extra={
            "total_pairs": len(all_pairs),
            "mid_seeded_pairs": mid_count,
            "alliance_seeded_pairs": alliance_count,
            "explicitly_unscored_pairs": unscored_count,
        },
    )
    return baseline_records
