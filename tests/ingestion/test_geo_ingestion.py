"""Tests for geo ingestion pipelines: military flights and strategic intel seed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import psycopg

from ingestion.geo import flights, intel_seed


def test_fetch_military_aircraft_parsing():
    sample_response = {
        "ac": [
            {
                "hex": "abc123",
                "r": "N12345",
                "t": "C17",
                "flight": "RCH123",
                "lat": 34.5,
                "lon": 45.6,
                "alt_baro": 30000,
                "gs": 450.5,
                "squawk": "1200",
            },
            {
                "hex": "def456",
                "lat": None,
                "lon": 12.0,
            },
            {
                "hex": "ground01",
                "lat": 10.0,
                "lon": 20.0,
                "alt_baro": "ground",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = sample_response
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_resp):
        rows = flights.fetch_military_aircraft()

    assert len(rows) == 2
    assert rows[0]["hex_code"] == "abc123"
    assert rows[0]["aircraft_type"] == "C17"
    assert rows[0]["altitude_ft"] == 30000
    assert rows[0]["ground_speed_kt"] == 450.5

    assert rows[1]["hex_code"] == "ground01"
    assert rows[1]["altitude_ft"] == 0


def test_intel_seed_data_integrity(test_db_url: str):
    res = intel_seed.run_intel_seed_sync()
    assert "sites_seeded" in res
    assert "routes_seeded" in res

    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM intel_sites")
            site_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM intel_routes")
            route_count = cur.fetchone()[0]

    assert site_count == len(intel_seed.SITES)
    assert route_count == len(intel_seed.CABLE_ROUTES)
