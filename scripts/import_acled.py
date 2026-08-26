"""CLI tool to fetch or import ACLED protest data into the War Impact Platform."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ingestion.common.config import get_settings
from ingestion.sources.acled_client import ACLEDClient, ingest_acled_csv_file, ingest_acled_events_into_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch or import ACLED protest data.")
    parser.add_argument("--csv", type=str, help="Path to exported ACLED CSV file (e.g. data/acled_india.csv)")
    parser.add_argument("--api", action="store_true", help="Fetch directly from ACLED REST API using credentials in .env")
    parser.add_argument("--country", type=str, default="India", help="Country filter (default: India)")
    parser.add_argument("--limit", type=int, default=500, help="Maximum events to fetch (default: 500)")

    args = parser.parse_args()
    db_url = get_settings().psycopg_database_url

    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.exists():
            print(f"Error: CSV file not found at {csv_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Importing ACLED records from {csv_path}...")
        count = ingest_acled_csv_file(str(csv_path), db_url)
        print(f"Successfully imported {count} ACLED protest records into database with source_provenance.")

    elif args.api:
        client = ACLEDClient()
        if not client.is_configured:
            print("Error: ACLED_EMAIL and ACLED_ACCESS_KEY must be set in .env", file=sys.stderr)
            sys.exit(1)
        print(f"Querying ACLED API for {args.country} (limit={args.limit})...")
        events = client.fetch_protest_events(country=args.country, limit=args.limit)
        if not events:
            print("No events returned from ACLED API (check access tier or credentials).", file=sys.stderr)
            sys.exit(1)
        count = ingest_acled_events_into_db(events, db_url)
        print(f"Successfully ingested {count} ACLED protest records into database with source_provenance.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
