"""Tests for naval fleet endpoints and data synchronization."""

from __future__ import annotations

import pytest
import psycopg
from httpx import ASGITransport, AsyncClient

from api.main import app
from ingestion.geo.naval_seed import seed_naval_fleets


@pytest.fixture(autouse=True)
def setup_naval_test_data(test_db_url: str):
    """Seed naval fleet data into test database."""
    with psycopg.connect(test_db_url) as conn:
        with conn.transaction():
            seed_naval_fleets(conn)


@pytest.mark.asyncio
async def test_get_naval_fleets_all() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/events/naval")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 20

    codes = {f["code"] for f in data}
    assert "US-CSG-LINCOLN" in codes
    assert "IN-CSG-VIKRANT" in codes
    assert "CN-CSG-SHANDONG" in codes

    lincoln = next(f for f in data if f["code"] == "US-CSG-LINCOLN")
    assert lincoln["flagship"] == "USS Abraham Lincoln (CVN-72)"
    assert lincoln["country_code"] == "USA"
    assert lincoln["fleet_type"] == "carrier_strike_group"
    assert lincoln["latitude"] > 0
    assert lincoln["longitude"] > 0


@pytest.mark.asyncio
async def test_get_naval_fleets_filtered() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/events/naval?country_code=IND")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    for f in data:
        assert f["country_code"] == "IND"
