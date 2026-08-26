"""Dedicated Safe Article Text Cache Repair & Backfill Tool.

Features:
- Default `--dry-run` mode: Performs zero writes, inspects cache state, reports metrics and eligible candidates.
- `--apply` mode: Requires `--confirm-production-repair <run-id>` token matching a preceding dry-run.
- Bounded batch size and async fetch execution with rate limits.
- Structured before/after status reports.
"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")
import argparse
import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import psycopg

from ingestion.common.config import get_settings
from ingestion.dashboard.url_normalizer import normalize_url
from models.sentiment.article_fetcher import (
    CachedArticle,
    fetch_single_article,
    MAX_FETCH_ATTEMPTS,
    DEFAULT_CONCURRENCY,
)

logger = logging.getLogger(__name__)
PENDING_CACHE_TOKEN_FILE = Path(__file__).parent / ".cache_repair_pending_token.json"
TOKEN_VALIDITY_MINUTES = 30


def get_cache_status(conn: psycopg.Connection) -> dict[str, Any]:
    """Audit current metrics and state of article_text_cache."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM article_text_cache;")
        total_rows = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM article_text_cache WHERE fetch_status = 'success' AND article_text IS NOT NULL;")
        success_rows = cur.fetchone()[0]

        # Stale successes: older than 14 days
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        cur.execute("SELECT COUNT(*) FROM article_text_cache WHERE fetch_status = 'success' AND (fetched_at < %s OR fetched_at IS NULL);", (stale_cutoff,))
        stale_successes = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM article_text_cache 
            WHERE fetch_status != 'success' 
              AND fetch_status != 'abandoned'
              AND (attempt_count < %s OR attempt_count IS NULL)
              AND (next_retry_at IS NULL OR next_retry_at <= NOW());
            """,
            (MAX_FETCH_ATTEMPTS,),
        )
        retry_eligible = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM article_text_cache 
            WHERE fetch_status = 'abandoned' OR attempt_count >= %s;
            """,
            (MAX_FETCH_ATTEMPTS,),
        )
        abandoned_rows = cur.fetchone()[0]

        # Status breakdown
        cur.execute("SELECT fetch_status, COUNT(*) FROM article_text_cache GROUP BY fetch_status;")
        status_breakdown = dict(cur.fetchall())

    return {
        "total_rows": total_rows,
        "success_rows": success_rows,
        "stale_successes": stale_successes,
        "retry_eligible_failures": retry_eligible,
        "permanently_abandoned": abandoned_rows,
        "status_breakdown": status_breakdown,
    }


def save_pending_token(token: str, db_url: str) -> None:
    data = {
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_url_hash": hashlib.sha256(db_url.encode()).hexdigest(),
    }
    with open(PENDING_CACHE_TOKEN_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def verify_and_consume_token(token_str: str, db_url: str) -> uuid.UUID:
    if not PENDING_CACHE_TOKEN_FILE.exists():
        raise RuntimeError(
            "NO PENDING DRY-RUN TOKEN: Run 'python -m scripts.repair_article_cache --dry-run' first."
        )

    try:
        with open(PENDING_CACHE_TOKEN_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise RuntimeError(f"Failed to read pending token: {exc}") from exc

    saved_token = data.get("token")
    created_at_str = data.get("created_at")
    db_hash = data.get("db_url_hash")
    current_hash = hashlib.sha256(db_url.encode()).hexdigest()

    if token_str != saved_token:
        raise RuntimeError(f"INVALID TOKEN: Supplied token does not match pending token '{saved_token}'.")
    if db_hash != current_hash:
        raise RuntimeError("DATABASE MISMATCH: Token was generated for a different database URL.")

    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str)
        if datetime.now(timezone.utc) - created_at > timedelta(minutes=TOKEN_VALIDITY_MINUTES):
            PENDING_CACHE_TOKEN_FILE.unlink(missing_ok=True)
            raise RuntimeError("TOKEN EXPIRED: Pending token has expired. Run --dry-run again.")

    PENDING_CACHE_TOKEN_FILE.unlink(missing_ok=True)
    return uuid.UUID(token_str)


def apply_cache_backfill(db_url: str, batch_size: int = 50) -> dict[str, Any]:
    """Execute bounded batch backfill of eligible cache records."""
    logger.info(f"Applying cache repair backfill (batch_size={batch_size})...")
    with psycopg.connect(db_url) as conn:
        before_status = get_cache_status(conn)

        # Backfill legacy records: set last_success_at on existing successful records
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE article_text_cache
                SET last_success_at = COALESCE(fetched_at, NOW()),
                    attempt_count = COALESCE(attempt_count, 1)
                WHERE fetch_status = 'success' AND last_success_at IS NULL;
                """
            )
            # Ensure all records have canonical_url
            cur.execute(
                """
                UPDATE article_text_cache
                SET canonical_url = source_url
                WHERE canonical_url IS NULL OR canonical_url = '';
                """
            )
            conn.commit()

            # Retrieve eligible items for refetch
            cur.execute(
                """
                SELECT source_url, canonical_url, COALESCE(attempt_count, 0)
                FROM article_text_cache
                WHERE fetch_status != 'success'
                  AND fetch_status != 'abandoned'
                  AND COALESCE(attempt_count, 0) < %s
                  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                LIMIT %s;
                """,
                (MAX_FETCH_ATTEMPTS, batch_size),
            )
            eligible_rows = cur.fetchall()

    refetched_count = 0
    if eligible_rows:
        logger.info(f"Refetching {len(eligible_rows)} eligible cache items...")
        async def _run_refetches() -> list[CachedArticle]:
            results = []
            sem = asyncio.Semaphore(DEFAULT_CONCURRENCY)
            async with httpx.AsyncClient(headers={"User-Agent": "WarImpactPlatform/1.0"}, follow_redirects=True, timeout=10.0) as client:
                async def _fetch(s_url: str, c_url: str, attempts: int) -> None:
                    async with sem:
                        res = await fetch_single_article(client, s_url, prior_attempts=attempts)
                        results.append(res)
                tasks = [_fetch(s_url, c_url, attempts) for s_url, c_url, attempts in eligible_rows]
                await asyncio.gather(*tasks, return_exceptions=True)
            return results

        fetched_articles = asyncio.run(_run_refetches())
        refetched_count = len(fetched_articles)

        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                for art in fetched_articles:
                    cur.execute(
                        """
                        INSERT INTO article_text_cache (
                            source_url, canonical_url, fetch_status, article_text, text_length,
                            attempt_count, last_error, next_retry_at, last_success_at, fetched_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (canonical_url) DO UPDATE SET
                            fetch_status = EXCLUDED.fetch_status,
                            article_text = COALESCE(EXCLUDED.article_text, article_text_cache.article_text),
                            text_length = CASE WHEN EXCLUDED.article_text IS NOT NULL THEN EXCLUDED.text_length ELSE article_text_cache.text_length END,
                            attempt_count = EXCLUDED.attempt_count,
                            last_error = EXCLUDED.last_error,
                            next_retry_at = EXCLUDED.next_retry_at,
                            last_success_at = COALESCE(EXCLUDED.last_success_at, article_text_cache.last_success_at),
                            fetched_at = NOW();
                        """,
                        (
                            art.source_url,
                            art.canonical_url,
                            art.fetch_status,
                            art.article_text,
                            art.text_length,
                            art.attempt_count,
                            art.last_error,
                            art.next_retry_at,
                            art.last_success_at,
                        ),
                    )
            conn.commit()

    with psycopg.connect(db_url) as conn:
        after_status = get_cache_status(conn)

    report = {
        "mode": "applied",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "before_status": before_status,
        "refetched_count": refetched_count,
        "after_status": after_status,
    }
    print(json.dumps(report, indent=2))
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Article Text Cache Repair and Diagnostic Tool.")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Run dry-run status audit (zero writes)")
    parser.add_argument("--apply", action="store_true", help="Apply cache repair backfill")
    parser.add_argument("--confirm-production-repair", type=str, help="Confirmation token from preceding dry run")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for refetching eligible failures")
    parser.add_argument("--db-url", type=str, help="Override database URL")
    args = parser.parse_args()

    db_url = args.db_url or get_settings().psycopg_database_url

    if args.apply:
        if not args.confirm_production_repair:
            print("ERROR: --apply requires --confirm-production-repair <run-id> from a preceding --dry-run.")
            sys.exit(1)

        token_str = args.confirm_production_repair.strip()
        try:
            confirmed_uuid = verify_and_consume_token(token_str, db_url)
        except RuntimeError as err:
            print(f"ERROR: {err}")
            sys.exit(1)

        apply_cache_backfill(db_url, batch_size=args.batch_size)
        return

    # Default Dry-Run Mode
    run_id = uuid.uuid4()
    save_pending_token(str(run_id), db_url)

    print("=" * 80)
    print("ARTICLE TEXT CACHE DIAGNOSTIC AUDIT (DRY-RUN MODE -- ZERO WRITES)")
    print(f"Run ID: {run_id}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    with psycopg.connect(db_url) as conn:
        status = get_cache_status(conn)

    report = {
        "run_id": str(run_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run",
        "cache_metrics": status,
    }
    print(json.dumps(report, indent=2))
    print("\nTo apply cache repair backfill, run:")
    print(f"  python -m scripts.repair_article_cache --apply --confirm-production-repair {run_id}\n")


if __name__ == "__main__":
    main()
