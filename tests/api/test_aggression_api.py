"""Integration tests for Bilateral Aggression REST API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_aggression_api_matrix_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/aggression/matrix")

    assert response.status_code == 200
    data = response.json()
    assert "total_pairs" in data
    assert "pairs" in data
    assert isinstance(data["pairs"], list)


@pytest.mark.asyncio
async def test_aggression_api_country_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/aggression/USA")

    assert response.status_code == 200
    pairs = response.json()
    assert isinstance(pairs, list)
    for p in pairs:
        assert p["country_a"] == "USA" or p["country_b"] == "USA"


@pytest.mark.asyncio
async def test_aggression_api_single_pair_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/aggression/USA/RUS")

    assert response.status_code in (200, 404)
    if response.status_code == 200:
        data = response.json()
        assert data["country_a"] == "RUS"
        assert data["country_b"] == "USA"


@pytest.mark.asyncio
async def test_aggression_api_invalid_country() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/aggression/INVALID_XYZ")

    assert response.status_code == 404
