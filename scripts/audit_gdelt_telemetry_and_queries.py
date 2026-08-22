"""Pre-Exhibition GDELT Database Telemetry and Unbounded Query Audit Script.

Deliverables:
1. Storage & Capacity Telemetry: Database size, gdelt_events size + indexes, daily growth rate, available disk space.
2. Unbounded Raw-GDELT Query Audit: Identifies unbounded queries (e.g., all-time MAX(event_date) in aggression), measures latency, documents post-exhibition aggregate replacement.
3. Post-Exhibition Partitioning & 400-day retention roadmap specification.
"""

from __future__ import annotations

import argparse
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import psycopg

load_dotenv()


def format_bytes(size_bytes: int | float) -> str:
    """Format bytes into human-readable MB / GB."""
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required.")
    return psycopg.connect(db_url.replace("postgresql+psycopg://", "postgresql://"))


def audit_storage_telemetry(conn: psycopg.Connection) -> dict:
    """Measure database size, gdelt_events table & index sizes, and daily growth rate."""
    telemetry = {}
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY;")

        # Database size
        cur.execute("SELECT pg_database_size(current_database());")
        db_size = cur.fetchone()[0]
        telemetry["database_size_bytes"] = db_size
        telemetry["database_size_human"] = format_bytes(db_size)

        # gdelt_events total, table, and index sizes
        cur.execute("SELECT pg_total_relation_size('gdelt_events'), pg_relation_size('gdelt_events'), pg_indexes_size('gdelt_events');")
        tot, tbl, idx = cur.fetchone()
        telemetry["gdelt_total_bytes"] = tot
        telemetry["gdelt_total_human"] = format_bytes(tot)
        telemetry["gdelt_table_bytes"] = tbl
        telemetry["gdelt_table_human"] = format_bytes(tbl)
        telemetry["gdelt_indexes_bytes"] = idx
        telemetry["gdelt_indexes_human"] = format_bytes(idx)

        # Per-index breakdown on gdelt_events
        cur.execute(
            """
            SELECT indexrelname, pg_relation_size(indexrelid) AS size_bytes
            FROM pg_stat_user_indexes
            WHERE relname = 'gdelt_events'
            ORDER BY size_bytes DESC;
            """
        )
        telemetry["indexes"] = [
            {"index_name": r[0], "size_bytes": r[1], "size_human": format_bytes(r[1])}
            for r in cur.fetchall()
        ]

        # Total rows and date range
        cur.execute("SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM gdelt_events;")
        cnt, min_d, max_d = cur.fetchone()
        telemetry["total_events"] = cnt
        telemetry["min_date"] = str(min_d)
        telemetry["max_date"] = str(max_d)

        # Average daily ingestion rate over recent 30 days
        cur.execute(
            """
            SELECT AVG(daily_count) FROM (
                SELECT event_date, COUNT(*) AS daily_count
                FROM gdelt_events
                WHERE event_date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY event_date
            ) sub;
            """
        )
        avg_daily_events = float(cur.fetchone()[0] or 100000)
        telemetry["avg_daily_events"] = int(avg_daily_events)

        # Average bytes per row
        avg_bytes_per_row = float(tot) / float(cnt) if cnt > 0 else 300.0
        telemetry["avg_bytes_per_event"] = round(avg_bytes_per_row, 1)

        # Estimated monthly growth
        monthly_growth_bytes = int(avg_daily_events * 30 * avg_bytes_per_row)
        telemetry["estimated_monthly_growth_human"] = format_bytes(monthly_growth_bytes)

    # Disk capacity inspection
    disk_stats = {}
    for drive in ["C:\\", "D:\\"]:
        if os.path.exists(drive):
            total, used, free = shutil.disk_usage(drive)
            disk_stats[drive] = {
                "total": format_bytes(total),
                "used": format_bytes(used),
                "free": format_bytes(free),
                "free_pct": round((free / total) * 100, 1),
            }
    telemetry["disk_stats"] = disk_stats

    return telemetry


def audit_unbounded_queries(conn: psycopg.Connection) -> list[dict]:
    """Identify and benchmark known unbounded queries across models."""
    unbounded_queries = [
        {
            "query_name": "Aggression Max Event Date (Bilateral Aggression Worker)",
            "source_file": "models/aggression/worker.py",
            "sql": "SELECT MAX(event_date) FROM gdelt_events;",
            "description": "Scans gdelt_events to determine latest ingested event date.",
            "post_exhibition_replacement": "Replace with lightweight query against country_pair_last_seen or _migration_meta.",
        },
        {
            "query_name": "All-time Distinct Country Pairs (Aggression Pipeline)",
            "source_file": "models/aggression/worker.py",
            "sql": """
                SELECT DISTINCT actor1_country_code, actor2_country_code 
                FROM gdelt_events 
                WHERE actor1_country_code IS NOT NULL AND actor2_country_code IS NOT NULL
                LIMIT 50;
            """,
            "description": "Scans bilateral country codes without partition boundary.",
            "post_exhibition_replacement": "Maintain distinct bilateral active pairs in country_pair_last_seen aggregate table.",
        },
        {
            "query_name": "Full Table Date Bounds (Cascade Detector)",
            "source_file": "models/cascade/detector.py",
            "sql": "SELECT MIN(score_date), MAX(score_date) FROM country_instability_index;",
            "description": "Scans country_instability_index for global date range bounds.",
            "post_exhibition_replacement": "Bounded range from active run config or index min/max.",
        },
    ]

    benchmark_results = []
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY;")
        for q in unbounded_queries:
            t0 = time.perf_counter()
            try:
                cur.execute(q["sql"])
                res = cur.fetchall()
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                benchmark_results.append({
                    **q,
                    "execution_time_ms": elapsed_ms,
                    "status": "PASS",
                    "sample_result": str(res[:2]) if res else "None",
                })
            except Exception as e:
                benchmark_results.append({
                    **q,
                    "execution_time_ms": -1,
                    "status": f"ERROR: {e}",
                    "sample_result": "N/A",
                })

    return benchmark_results


def main() -> None:
    print("=" * 80)
    print("PRE-EXHIBITION GDELT STORAGE TELEMETRY & QUERY AUDIT")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    with get_db_connection() as conn:
        telemetry = audit_storage_telemetry(conn)
        queries = audit_unbounded_queries(conn)

    print("\n1. DATABASE & GDELT_EVENTS STORAGE CAPACITY:")
    print(f"  * Total PostgreSQL Database Size : {telemetry['database_size_human']}")
    print(f"  * Total gdelt_events Table + Idx : {telemetry['gdelt_total_human']}")
    print(f"    - Table Heap Size              : {telemetry['gdelt_table_human']}")
    print(f"    - Total Index Size             : {telemetry['gdelt_indexes_human']}")
    print(f"  * Total Event Records Ingested   : {telemetry['total_events']:,} rows")
    print(f"  * Event Date Coverage            : {telemetry['min_date']} to {telemetry['max_date']}")
    print(f"  * Ingestion Rate (30d avg)       : ~{telemetry['avg_daily_events']:,} events/day")
    print(f"  * Estimated Monthly Growth       : ~{telemetry['estimated_monthly_growth_human']}/month")

    print("\n  Per-Index Breakdown on gdelt_events:")
    for idx in telemetry["indexes"]:
        print(f"    - {idx['index_name']:<40} : {idx['size_human']}")

    print("\n  Host Filesystem Free Space:")
    for drive, stats in telemetry["disk_stats"].items():
        print(f"    - {drive} : Free {stats['free']} / {stats['total']} ({stats['free_pct']}% available)")

    print("\n2. UNBOUNDED RAW-GDELT QUERY BENCHMARK & AUDIT:")
    for q in queries:
        print(f"\n  [{q['query_name']}]")
        print(f"    * Source File    : {q['source_file']}")
        print(f"    * Latency        : {q['execution_time_ms']} ms ({q['status']})")
        print(f"    * Post-Exhibition: {q['post_exhibition_replacement']}")

    print("\n3. POST-EXHIBITION PARTITIONING & 400-DAY RETENTION SPECIFICATION:")
    print("  * Architecture     : PostgreSQL Declarative Partitioning 'PARTITION BY RANGE (event_date)'.")
    print("  * Partition Window : Monthly partitions (e.g., gdelt_events_y2026m08).")
    print("  * Retention Window : 400 operational days retained in primary PostgreSQL database.")
    print("  * Cold Storage     : Monthly partitions > 400 days exported to compressed Parquet with SHA-256 manifest.")
    print("  * Pre-Conditions   : Pre-exhibition database remains intact without table rebuild or data deletion.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
