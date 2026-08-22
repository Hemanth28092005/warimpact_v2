"""Integration tests for Phase 6a Dashboard REST API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from scripts.seed_dashboard_data import main as seed_dashboard_data
from models.trade_routes.routes import update_india_trade_routes


@pytest.fixture(autouse=True)
def setup_api_test_data(test_db_url: str):
    """Ensure static dashboard tables and routes are seeded in isolated test database."""
    seed_dashboard_data(db_url=test_db_url)
    update_india_trade_routes(db_url=test_db_url)


@pytest.mark.asyncio
async def test_dashboard_chokepoints_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard/chokepoints")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 13
    codes = {c["code"] for c in data}
    assert "HORMUZ" in codes
    assert "MALACCA" in codes
    assert "SUEZ" in codes


@pytest.mark.asyncio
async def test_dashboard_trade_routes_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard/trade-routes")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "commodity_code" in data[0]
    assert "risk_score" in data[0]


@pytest.mark.asyncio
async def test_dashboard_protests_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard/protests")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 50


@pytest.mark.asyncio
async def test_dashboard_regional_headlines_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard/regional-headlines")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 70


@pytest.mark.asyncio
async def test_dashboard_government_actions_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard/government-actions")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 10


@pytest.mark.asyncio
async def test_dashboard_commodities_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard/commodities")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 30
