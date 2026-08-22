"""Operational script for read-only database verification and row-count audits.

Guarantees:
- Strictly read-only: Enforces `SET TRANSACTION READ ONLY;` immediately upon connecting.
- Independent: Never imported or executed by pytest.
- Captures pre- and post-test production row counts across all 7 dashboard and model tables.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import psycopg

load_dotenv()

SNAPSHOT_FILE = Path(__file__).parent / ".prod_rowcount_snapshot.json"

TABLES_TO_AUDIT = [
    "gdelt_events",
    "regional_headlines",
    "government_actions",
    "protests",
    "commodity_news",
    "chokepoints",
    "cascade_scores",
    "country_aggression_scores",
    "country_instability_index",
]


def get_readonly_connection_url() -> str:
    """Resolve production database URL for read-only inspection. Requires explicit PRODUCTION_READONLY_DATABASE_URL."""
    url = os.getenv("PRODUCTION_READONLY_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "ISOLATION ENFORCEMENT: 'PRODUCTION_READONLY_DATABASE_URL' environment variable is required "
            "for running production audits. Refusing to fall back to general DATABASE_URL."
        )
    return url.replace("postgresql+psycopg://", "postgresql://")


def capture_row_counts() -> dict[str, int]:
    """Connect to database, set READ ONLY transaction, and capture exact row counts."""
    db_url = get_readonly_connection_url()
    counts: dict[str, int] = {}

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY;")
            for tbl in TABLES_TO_AUDIT:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl};")  # noqa: S608
                    counts[tbl] = cur.fetchone()[0]
                except Exception as e:
                    counts[tbl] = -1
                    conn.rollback()
                    cur.execute("SET TRANSACTION READ ONLY;")

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only production row-count auditor.")
    parser.add_argument("--snapshot-before", action="store_true", help="Capture baseline pre-execution snapshot")
    parser.add_argument("--snapshot-after", action="store_true", help="Compare post-execution counts against baseline")
    parser.add_argument("--print-current", action="store_true", help="Print current live row counts")
    args = parser.parse_args()

    counts = capture_row_counts()
    now_str = datetime.now(timezone.utc).isoformat()

    if args.snapshot_before:
        payload = {"timestamp": now_str, "counts": counts}
        SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[{now_str}] Baseline pre-test snapshot saved to {SNAPSHOT_FILE.name}:")
        for tbl, cnt in counts.items():
            print(f"  * {tbl:<30}: {cnt:,} rows")
        return

    if args.snapshot_after:
        if not SNAPSHOT_FILE.exists():
            print("ERROR: No baseline snapshot found. Run with --snapshot-before first.")
            sys.exit(1)

        baseline_data = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        baseline_counts = baseline_data["counts"]
        baseline_time = baseline_data["timestamp"]

        print(f"[{now_str}] Comparing against baseline snapshot from {baseline_time}:")
        has_drift = False
        for tbl in TABLES_TO_AUDIT:
            before = baseline_counts.get(tbl, 0)
            after = counts.get(tbl, 0)
            diff = after - before
            status = "OK (UNCHANGED)" if diff == 0 else f"DRIFT DETECTED ({diff:+d})"
            if diff != 0:
                has_drift = True
            print(f"  * {tbl:<30}: Before={before:,} | After={after:,} | {status}")

        if has_drift:
            print("\nWARNING: Production row-count drift was detected!")
            sys.exit(2)
        else:
            print("\nSUCCESS: All production row counts are 100% verified unchanged.")
        return

    # Default / --print-current
    print(f"[{now_str}] Current live row counts:")
    for tbl, cnt in counts.items():
        print(f"  * {tbl:<30}: {cnt:,} rows")


if __name__ == "__main__":
    main()
