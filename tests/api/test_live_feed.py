"""Unit & integration tests for Live Escalation Feed API endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.live_feed import _dedupe_and_format_events

client = TestClient(app)


def test_invalid_region_returns_400() -> None:
    """Requesting an unsupported region must return 400 Bad Request."""
    response = client.get("/api/v1/live-feed/invalid_region")
    assert response.status_code == 400
    assert "Invalid region 'invalid_region'" in response.json()["detail"]


def test_valid_region_returns_200() -> None:
    """Valid regions should return 200 OK with correct schema even if empty."""
    for region in ["india", "usa", "europe", "middle_east"]:
        response = client.get(f"/api/v1/live-feed/{region}?bypass_cache=true")
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == region
        assert "total_escalations" in data
        assert isinstance(data["items"], list)


def test_deduplication_logic() -> None:
    """Confirm near-duplicate events (same actor pair + event_code) collapse into single item with count."""
    sample_events = [
        {
            "global_event_id": 1,
            "event_date": "2026-07-31",
            "ingested_at": "2026-07-31T10:00:00+00:00",
            "actor1_code": "ISR",
            "actor2_code": "SYR",
            "event_code": "190",
            "num_mentions": 10,
        },
        {
            "global_event_id": 2,
            "event_date": "2026-07-31",
            "ingested_at": "2026-07-31T10:05:00+00:00",
            "actor1_code": "ISR",
            "actor2_code": "SYR",
            "event_code": "190",
            "num_mentions": 45,  # Higher mention count instance
        },
        {
            "global_event_id": 3,
            "event_date": "2026-07-31",
            "ingested_at": "2026-07-31T10:10:00+00:00",
            "actor1_code": "USA",
            "actor2_code": "RUS",
            "event_code": "110",
            "num_mentions": 5,
        },
    ]

    deduped = _dedupe_and_format_events(sample_events)
    assert len(deduped) == 2

    # ISR-SYR event 190 group should have count = 2, and primary item should have num_mentions = 45
    isr_syr = [item for item in deduped if item["actor1_code"] == "ISR" and item["actor2_code"] == "SYR"][0]
    assert isr_syr["num_mentions"] == 45
    assert isr_syr["related_mentions_count"] == 2
