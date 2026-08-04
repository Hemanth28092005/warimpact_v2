"""API unit tests for Phase 4 Cascade endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_get_cascade_scores_invalid_code() -> None:
    response = client.get("/api/v1/cascade/INVALID_CODE")
    assert response.status_code == 400
    assert "Invalid country_code" in response.json()["detail"]


def test_get_cascade_scores_valid() -> None:
    response = client.get("/api/v1/cascade/USA?window_days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["country_code"] == "USA"
    assert data["window_days"] == 7
    assert "total_pairs" in data
    assert isinstance(data["pairs"], list)
