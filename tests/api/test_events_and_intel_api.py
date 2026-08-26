"""Tests for Phase 2 events, flights, intel sites/routes, and brief endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from ingestion.geo.intel_seed import run_intel_seed_sync
from ingestion.geo.flights import upsert_flights
import psycopg
from datetime import datetime, timezone
from ingestion.common.config import get_settings


@pytest.fixture(autouse=True)
def setup_phase2_test_data(test_db_url: str):
    """Seed intel sites, routes and a dummy flight track in test database."""
    run_intel_seed_sync()
    with psycopg.connect(test_db_url) as conn:
        with conn.transaction():
            upsert_flights(
                conn,
                [
                    {
                        "hex_code": "TEST01",
                        "registration": "REG-01",
                        "aircraft_type": "F35",
                        "callsign": "VIPER1",
                        "latitude": 32.5,
                        "longitude": 35.8,
                        "altitude_ft": 25000,
                        "ground_speed_kt": 480.0,
                        "squawk": "7700",
                        "observed_at": datetime.now(timezone.utc),
                    }
                ],
            )


@pytest.mark.asyncio
async def test_flights_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/events/flights")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    sample = [f for f in data if f["hex"] == "TEST01"][0]
    assert sample["callsign"] == "VIPER1"
    assert sample["aircraft_type"] == "F35"
    assert sample["altitude_ft"] == 25000


@pytest.mark.asyncio
async def test_intel_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/events/intel")

    assert response.status_code == 200
    data = response.json()
    assert "sites" in data
    assert "routes" in data
    assert len(data["sites"]) >= 40
    assert len(data["routes"]) >= 10

    categories = {s["category"] for s in data["sites"]}
    assert "military_base" in categories
    assert "nuclear_site" in categories
    assert "spaceport" in categories

    route_cats = {r["category"] for r in data["routes"]}
    assert "undersea_cable" in route_cats


@pytest.mark.asyncio
async def test_earthquakes_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/events/earthquakes")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_prediction_markets_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/events/prediction-markets")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
