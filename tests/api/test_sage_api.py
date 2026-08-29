"""Integration tests for Sage Geopolitical Intelligence & Advisory REST API endpoints.

These tests are strictly read-only and verify endpoint structure, validation,
and response schemas.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_sage_suggestions_returns_categories() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sage/suggestions")

    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert len(data["categories"]) == 5
    expected = {
        "Crisis & Conflict Analysis",
        "Maritime Chokepoint Disruption",
        "Commodities, Energy & Trade Impact",
        "Strategic Advisory & Risk Hedging",
        "Contagion & Platform Data",
    }
    assert {c["category"] for c in data["categories"]} == expected
    for cat in data["categories"]:
        assert cat["prompts"], f"{cat['category']} has no prompt starters"
        assert cat["emoji"], f"{cat['category']} has no emoji icon"


@pytest.mark.asyncio
async def test_sage_context_returns_live_signals() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sage/context")

    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "defcon_level",
        "top_volatile_countries",
        "chokepoints",
        "top_aggression_pairs",
        "high_risk_trade_routes",
        "recent_headlines",
        "data_gaps",
    ):
        assert key in data


@pytest.mark.asyncio
async def test_sage_chat_rejects_empty_message() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/sage/chat", json={"message": "   ", "history": []})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sage_chat_returns_structured_response() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/sage/chat",
            json={"message": "What is the current global instability and DEFCON status?", "history": []},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["reply"], str) and len(data["reply"].strip()) > 0
    assert "model_used" in data
    assert isinstance(data["telemetry_highlights"], list)
    assert isinstance(data["suggested_followups"], list)
    assert isinstance(data["latency_ms"], int)


@pytest.mark.asyncio
async def test_sage_chat_entity_deep_dive() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/sage/chat",
            json={
                "message": "What is the disruption threat at the Strait of Hormuz and Red Sea?",
                "history": [],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["reply"], str)
    assert len(data["suggested_followups"]) > 0
