"""Safe Dashboard Feed Repair & Diagnostic Tool.

Features:
- Default `--dry-run` mode: Performs zero writes, produces a detailed audit report with proposed operations.
- `--apply` mode: Requires `--confirm-production-repair <run-id>` token to prevent accidental execution.
- Generates structured repair audit logging.
"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")
import argparse
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
import psycopg

from ingestion.common.config import get_settings
from ingestion.dashboard.tasks import (
    run_regional_headlines,
    run_government_actions,
    run_protests,
)
from models.chokepoints.disruption import calculate_chokepoint_disruptions
from models.commodities.news import update_commodity_news
from models.trade_routes.routes import update_india_trade_routes

load_dotenv()
AUDIT_LOG_FILE = Path(__file__).parent / "dashboard_repair_audit.jsonl"


def _get_existing_columns(cur, table_name: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s;", (table_name,))
    return {r[0] for r in cur.fetchall()}


def generate_repair_report(conn: psycopg.Connection, run_id: uuid.UUID) -> dict:
    """Analyze current dashboard feed states and calculate proposed repair metrics."""
    report = {
        "run_id": str(run_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run",
        "feeds": {},
    }

    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY;")

        # 1. Regional Headlines
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT region) FROM regional_headlines;")
        rh_cnt, rh_regions = cur.fetchone()
        cur.execute("SELECT region, rank, headline FROM regional_headlines ORDER BY region, rank LIMIT 3;")
        rh_samples = [{"region": r[0], "rank": r[1], "headline": r[2]} for r in cur.fetchall()]
        report["feeds"]["regional_headlines"] = {
            "current_count": rh_cnt,
            "distinct_regions": rh_regions,
            "sample_records": rh_samples,
            "proposed_action": "Atomic snapshot refresh across 7 regions",
        }

        # 2. Government Actions
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT action_type) FROM government_actions;")
        ga_cnt, ga_types = cur.fetchone()
        cur.execute("SELECT rank, headline, action_type FROM government_actions ORDER BY rank LIMIT 3;")
        ga_samples = [{"rank": r[0], "headline": r[1], "action_type": r[2]} for r in cur.fetchall()]
        report["feeds"]["government_actions"] = {
            "current_count": ga_cnt,
            "distinct_action_types": ga_types,
            "sample_records": ga_samples,
            "proposed_action": "Actor validation and canonical action_type snapshot refresh (top 10)",
        }

        # 3. Protests
        pr_cols = _get_existing_columns(cur, "protests")
        cur.execute("SELECT COUNT(*) FROM protests;")
        pr_cnt = cur.fetchone()[0]
        cur.execute("SELECT city, event_severity, headline FROM protests ORDER BY event_severity DESC LIMIT 3;")
        pr_samples = [{"city": r[0], "severity": float(r[1] or 0), "headline": r[2]} for r in cur.fetchall()]
        report["feeds"]["protests"] = {
            "current_count": pr_cnt,
            "has_location_hierarchy": "location_name" in pr_cols,
            "sample_records": pr_samples,
            "proposed_action": "Multi-factor normalized severity recalculation and geography hierarchy assignment",
        }

        # 4. Commodity News
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT commodity_code) FROM commodity_news;")
        cn_cnt, cn_commodities = cur.fetchone()
        cur.execute("SELECT commodity_code, rank, headline FROM commodity_news ORDER BY commodity_code, rank LIMIT 3;")
        cn_samples = [{"commodity": r[0], "rank": r[1], "headline": r[2]} for r in cur.fetchall()]
        report["feeds"]["commodity_news"] = {
            "current_count": cn_cnt,
            "distinct_commodities": cn_commodities,
            "sample_records": cn_samples,
            "proposed_action": "Explicit taxonomy matching and staged atomic publishing",
        }

        # 5. Chokepoints
        cur.execute("SELECT COUNT(*), COUNT(CASE WHEN status = 'green' THEN 1 END), COUNT(CASE WHEN status = 'yellow' THEN 1 END), COUNT(CASE WHEN status = 'red' THEN 1 END) FROM chokepoints;")
        chk_cnt, chk_g, chk_y, chk_r = cur.fetchone()
        report["feeds"]["chokepoints"] = {
            "current_count": chk_cnt,
            "status_breakdown": {"green": chk_g, "yellow": chk_y, "red": chk_r},
            "proposed_action": "Geodesic threat recalculation and child evidence logging",
        }

    return report


def apply_repairs(db_url: str, run_id: uuid.UUID) -> dict:
    """Execute live repair operations within safe managed transactions."""
    start_time = datetime.now(timezone.utc)
    results = {}

    print(f"[{start_time.isoformat()}] Applying live repairs for run {run_id}...")

    # 1. Refresh Regional Headlines
    print("  -> Ingesting regional headlines...")
    rh_res = run_regional_headlines(db_url=db_url)
    results["regional_headlines"] = rh_res

    # 2. Refresh Government Actions
    print("  -> Ingesting Indian government actions...")
    ga_res = run_government_actions(db_url=db_url)
    results["government_actions"] = ga_res

    # 3. Refresh Protests
    print("  -> Ingesting Indian civil protests...")
    pr_res = run_protests(db_url=db_url)
    results["protests"] = pr_res

    # 4. Refresh Commodity News
    print("  -> Ingesting commodity news with staged atomic snapshots...")
    cn_res = update_commodity_news(db_url=db_url)
    results["commodity_news"] = cn_res

    # 5. Refresh Chokepoints
    print("  -> Recalculating chokepoint disruptions...")
    chk_res = calculate_chokepoint_disruptions(db_url=db_url)
    results["chokepoints"] = chk_res

    # 6. Refresh India Trade Routes
    print("  -> Recalculating India trade route risks...")
    tr_res = update_india_trade_routes(db_url=db_url)
    results["trade_routes"] = tr_res

    completed_time = datetime.now(timezone.utc)
    audit_entry = {
        "run_id": str(run_id),
        "started_at": start_time.isoformat(),
        "completed_at": completed_time.isoformat(),
        "mode": "applied",
        "results": results,
    }

    # Append to audit log
    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(audit_entry) + "\n")

    print(f"[{completed_time.isoformat()}] Live repairs successfully applied. Audit log appended to {AUDIT_LOG_FILE.name}.")
    return audit_entry


PENDING_TOKEN_FILE = Path(__file__).parent / ".dashboard_repair_pending_token.json"
TOKEN_VALIDITY_MINUTES = 30


def save_pending_token(token: str, db_url: str) -> None:
    """Save pending dry-run confirmation token with expiration timestamp and database hash."""
    import hashlib
    data = {
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_url_hash": hashlib.sha256(db_url.encode()).hexdigest(),
    }
    with open(PENDING_TOKEN_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def verify_and_consume_token(token_str: str, db_url: str) -> uuid.UUID:
    """Verify that token was produced by a preceding dry-run within TTL, then consume it."""
    import hashlib
    if not PENDING_TOKEN_FILE.exists():
        raise RuntimeError(
            "NO PENDING DRY-RUN TOKEN: Refusing to apply repairs without a preceding dry-run! "
            "Run 'python -m scripts.repair_dashboard_feeds --dry-run' first."
        )

    try:
        with open(PENDING_TOKEN_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise RuntimeError(f"Failed to read pending token file: {exc}") from exc

    saved_token = data.get("token")
    created_at_str = data.get("created_at")
    db_hash = data.get("db_url_hash")
    current_hash = hashlib.sha256(db_url.encode()).hexdigest()

    if token_str != saved_token:
        raise RuntimeError(
            f"INVALID TOKEN: Provided token '{token_str}' does not match the pending dry-run token '{saved_token}'."
        )

    if db_hash != current_hash:
        raise RuntimeError(
            "DATABASE MISMATCH: Pending token was generated against a different database connection URL."
        )

    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str)
        age = datetime.now(timezone.utc) - created_at
        if age > timedelta(minutes=TOKEN_VALIDITY_MINUTES):
            PENDING_TOKEN_FILE.unlink(missing_ok=True)
            raise RuntimeError(
                f"TOKEN EXPIRED: Pending token is {int(age.total_seconds() // 60)} minutes old "
                f"(max validity is {TOKEN_VALIDITY_MINUTES} minutes). Run --dry-run again."
            )

    # Token is valid - consume it so it cannot be reused
    PENDING_TOKEN_FILE.unlink(missing_ok=True)
    return uuid.UUID(token_str)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Dashboard Feeds Repair & Backfill Tool.")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Execute in dry-run mode (no writes)")
    parser.add_argument("--apply", action="store_true", help="Apply repairs to active database")
    parser.add_argument("--confirm-production-repair", type=str, help="Confirmation run-id token required when applying repairs")
    parser.add_argument("--db-url", type=str, help="Override database URL (defaults to get_settings().psycopg_database_url)")
    args = parser.parse_args()

    db_url = args.db_url or get_settings().psycopg_database_url

    if args.apply:
        if not args.confirm_production_repair:
            print("ERROR: --apply requires an explicit confirmation token generated by a preceding --dry-run.")
            print("Usage: python -m scripts.repair_dashboard_feeds --apply --confirm-production-repair <run-id>")
            sys.exit(1)

        token_str = args.confirm_production_repair.strip()
        try:
            confirmed_uuid = verify_and_consume_token(token_str, db_url)
        except RuntimeError as err:
            print(f"ERROR: {err}")
            sys.exit(1)

        apply_repairs(db_url, confirmed_uuid)
        return

    # Default Dry-Run Mode
    run_id = uuid.uuid4()
    save_pending_token(str(run_id), db_url)

    print("=" * 80)
    print("DASHBOARD FEEDS REPAIR & DIAGNOSTIC AUDIT (DRY-RUN MODE -- ZERO WRITES)")
    print(f"Run ID: {run_id}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    with psycopg.connect(db_url) as conn:
        report = generate_repair_report(conn, run_id)

    print(json.dumps(report, indent=2))
    print("\nTo apply these repairs, run:")
    print(f"  python -m scripts.repair_dashboard_feeds --apply --confirm-production-repair {run_id}\n")


if __name__ == "__main__":
    main()
