"""World Bank Pink Sheet Commodity Markets Client and Parser.

Handles:
- Fetching published monthly commodity prices dataset (CMO-Historical-Data-Monthly.xlsx).
- Parsing historical monthly price observations using stdlib zipfile + XML parser (zero external dependency).
- Storing observations in `commodity_market_observations` table with `source_name = 'world_bank_pink_sheet'` and `frequency = 'monthly'`.
- Additive, non-gating market corroboration.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timezone
from typing import Any
import httpx
import psycopg

logger = logging.getLogger(__name__)

WB_PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
)

# Mapping from World Bank column names to platform tracked commodity codes
WB_COMMODITY_MAP: dict[str, str] = {
    "crude oil, brent": "PETROLEUM_CRUDE",
    "crude oil, wti": "PETROLEUM_CRUDE",
    "crude oil, average": "PETROLEUM_CRUDE",
    "coal, australian": "COAL_COKE",
    "coal, south african": "COAL_COKE",
    "natural gas, us": "LNG_NATURAL_GAS",
    "natural gas, europe": "LNG_NATURAL_GAS",
    "liquefied natural gas, japan": "LNG_NATURAL_GAS",
    "gold": "GOLD",
    "copper": "COPPER_REFINED",
    "aluminum": "ALUMINUM_UNWROUGHT",
    "wheat, us hrw": "WHEAT",
    "wheat, us srw": "WHEAT",
    "rice, thai 5%": "RICE_BASMATI",
    "palm oil": "VEGETABLE_OILS",
    "soybean oil": "VEGETABLE_OILS",
    "soybeans": "SOYBEAN_MEAL",
    "dap": "FERTILIZERS",
    "urea, e. europe": "FERTILIZERS",
    "potassium chloride": "FERTILIZERS",
    "iron ore, cfr spot": "IRON_ORE",
}


def _col_idx_to_letter(idx: int) -> str:
    """Convert 0-based column index to Excel column letters (A, B, ..., Z, AA, AB...)."""
    result = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def _cell_col_index(cell_ref: str) -> int:
    """Extract 0-based column index from cell reference string (e.g. 'C12' -> 2)."""
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    letters = match.group(1)
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col - 1


class WorldBankPinkSheetClient:
    """World Bank Pink Sheet monthly commodity dataset fetcher and parser."""

    def __init__(self, data_url: str = WB_PINK_SHEET_URL) -> None:
        self.data_url = data_url

    def fetch_monthly_observations(
        self,
        recent_months_count: int = 12,
        timeout_seconds: float = 30.0,
    ) -> list[dict[str, Any]]:
        """Fetch and parse monthly commodity price series from World Bank XLSX."""
        try:
            with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                resp = client.get(self.data_url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    logger.warning(f"World Bank Pink Sheet fetch returned HTTP {resp.status_code}")
                    return []
                content = resp.content
        except Exception as err:
            logger.error(f"Failed to fetch World Bank Pink Sheet: {err}")
            return []

        observations: list[dict[str, Any]] = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

            # 1. Read shared strings
            sst: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root.findall(f"{ns}si"):
                    t = si.find(f"{ns}t")
                    sst.append(t.text if t is not None and t.text else "")

            # 2. Parse Sheet2 (Monthly Prices)
            if "xl/worksheets/sheet2.xml" not in zf.namelist():
                logger.warning("Sheet2.xml not found in World Bank XLSX")
                return []

            root = ET.fromstring(zf.read("xl/worksheets/sheet2.xml"))
            rows = root.findall(f"{ns}sheetData/{ns}row")
            if len(rows) < 6:
                return []

            # Row 4 is header row with commodity names
            # Row 5 is units row
            header_row = rows[4]
            unit_row = rows[5]

            headers_by_col: dict[int, str] = {}
            for c in header_row.findall(f"{ns}c"):
                ref = c.get("r", "")
                col_idx = _cell_col_index(ref)
                t = c.get("t")
                v = c.find(f"{ns}v")
                if v is not None and v.text is not None:
                    val = sst[int(v.text)] if t == "s" and int(v.text) < len(sst) else v.text
                    if val:
                        headers_by_col[col_idx] = val.strip()

            units_by_col: dict[int, str] = {}
            for c in unit_row.findall(f"{ns}c"):
                ref = c.get("r", "")
                col_idx = _cell_col_index(ref)
                t = c.get("t")
                v = c.find(f"{ns}v")
                if v is not None and v.text is not None:
                    val = sst[int(v.text)] if t == "s" and int(v.text) < len(sst) else v.text
                    if val:
                        units_by_col[col_idx] = val.strip()

            # Data rows start at index 6
            data_rows = rows[6:]
            target_data_rows = data_rows[-recent_months_count:] if len(data_rows) > recent_months_count else data_rows

            for row in target_data_rows:
                cells = row.findall(f"{ns}c")
                if not cells:
                    continue

                row_vals_by_col: dict[int, str] = {}
                for c in cells:
                    ref = c.get("r", "")
                    col_idx = _cell_col_index(ref)
                    t = c.get("t")
                    v = c.find(f"{ns}v")
                    if v is not None and v.text is not None:
                        val = sst[int(v.text)] if t == "s" and int(v.text) < len(sst) else v.text
                        if val:
                            row_vals_by_col[col_idx] = val.strip()

                period_str = row_vals_by_col.get(0, "")
                if not period_str or "M" not in period_str:
                    continue

                # Parse YYYYMmm to date (e.g. 2026M07 -> 2026-07-01)
                try:
                    parts = period_str.split("M")
                    obs_date = date(int(parts[0]), int(parts[1]), 1)
                except Exception:
                    continue

                for col_idx, raw_val in row_vals_by_col.items():
                    if col_idx == 0:
                        continue
                    header_name = headers_by_col.get(col_idx, "")
                    if not header_name:
                        continue

                    # Match header to commodity code
                    clean_header = header_name.lower().replace("**", "").strip()
                    matched_code = next(
                        (code for k, code in WB_COMMODITY_MAP.items() if k in clean_header),
                        None
                    )
                    if not matched_code:
                        continue

                    try:
                        num_val = float(raw_val)
                    except ValueError:
                        continue

                    unit_str = units_by_col.get(col_idx, "USD")
                    series_id = f"wb_{clean_header.replace(' ', '_').replace(',', '')}"

                    observations.append({
                        "source_name": "world_bank_pink_sheet",
                        "series_id": series_id,
                        "commodity_code": matched_code,
                        "observation_date": obs_date,
                        "frequency": "monthly",
                        "value": num_val,
                        "unit": unit_str,
                        "source_url": self.data_url,
                        "raw_header": header_name,
                    })

        except Exception as err:
            logger.error(f"Error parsing World Bank Pink Sheet XLSX: {err}")

        return observations


def sync_world_bank_observations(db_url: str) -> int:
    """Fetch and sync World Bank Pink Sheet observations into database."""
    client = WorldBankPinkSheetClient()
    observations = client.fetch_monthly_observations(recent_months_count=24)
    if not observations:
        return 0

    inserted_count = 0
    now_utc = datetime.now(timezone.utc)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for obs in observations:
                cur.execute(
                    """
                    INSERT INTO commodity_market_observations (
                        source_name, series_id, commodity_code, observation_date,
                        frequency, value, unit, retrieved_at, source_url
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_name, series_id, observation_date)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        retrieved_at = EXCLUDED.retrieved_at;
                    """,
                    (
                        obs["source_name"],
                        obs["series_id"],
                        obs["commodity_code"],
                        obs["observation_date"],
                        obs["frequency"],
                        obs["value"],
                        obs["unit"],
                        now_utc,
                        obs["source_url"],
                    ),
                )
                inserted_count += 1

                # Record provenance
                payload_str = json.dumps({
                    "series_id": obs["series_id"],
                    "commodity": obs["commodity_code"],
                    "value": obs["value"],
                    "unit": obs["unit"],
                    "date": str(obs["observation_date"]),
                }, sort_keys=True)
                payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

                cur.execute(
                    """
                    INSERT INTO source_provenance (
                        source_name, source_record_id, publication_date,
                        evidence_role, payload_hash, raw_payload, entity_type, entity_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_name, source_record_id, entity_type)
                    DO UPDATE SET
                        retrieved_at = NOW(),
                        payload_hash = EXCLUDED.payload_hash,
                        raw_payload = EXCLUDED.raw_payload;
                    """,
                    (
                        "world_bank_pink_sheet",
                        f"{obs['series_id']}_{obs['observation_date']}",
                        obs["observation_date"],
                        "corroborating_benchmark",
                        payload_hash,
                        payload_str,
                        "commodity_observation",
                        f"{obs['commodity_code']}_{obs['observation_date']}",
                    ),
                )

        conn.commit()

    return inserted_count
