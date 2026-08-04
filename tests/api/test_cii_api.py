"""Integration tests for FastAPI CII endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "operational" in response.json()["message"]


@patch("api.routes.cii.open_async_connection")
def test_get_latest_cii_scores(mock_open_conn: MagicMock) -> None:
    mock_conn = MagicMock()
    mock_cur = AsyncMock()
    mock_cur.fetchall.return_value = [
        ("USA", "2026-07-27", 43.5, "cii-v1.0.0", 38.5, 48.5, {"escalation_probability": 0.12}, "2026-07-27T15:00:00+00:00"),
    ]
    mock_cur_cm = MagicMock()
    mock_cur_cm.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_cur_cm.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor.return_value = mock_cur_cm

    mock_conn_cm = MagicMock()
    mock_conn_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn_cm.__aexit__ = AsyncMock(return_value=None)
    mock_open_conn.return_value = mock_conn_cm

    response = client.get("/api/v1/cii/latest")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["country_code"] == "USA"
    assert data[0]["cii_score"] == 43.5


@patch("api.routes.cii.open_async_connection")
def test_get_country_cii_history(mock_open_conn: MagicMock) -> None:
    mock_conn = MagicMock()
    mock_cur = AsyncMock()
    mock_cur.fetchall.return_value = [
        ("USA", "2026-07-27", 43.5, "cii-v1.0.0", 38.5, 48.5, {"escalation_probability": 0.12}, "2026-07-27T15:00:00+00:00"),
    ]
    mock_cur_cm = MagicMock()
    mock_cur_cm.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_cur_cm.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor.return_value = mock_cur_cm

    mock_conn_cm = MagicMock()
    mock_conn_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn_cm.__aexit__ = AsyncMock(return_value=None)
    mock_open_conn.return_value = mock_conn_cm

    response = client.get("/api/v1/cii/USA")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["country_code"] == "USA"

    response = client.get("/api/v1/cii/USA")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["country_code"] == "USA"
