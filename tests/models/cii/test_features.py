"""Unit tests for Phase 3 CII feature engineering."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cii.features import FEATURE_COLUMNS, extract_country_features_for_date


@pytest.mark.asyncio
async def test_extract_country_features_for_date_handles_missing_days() -> None:
    mock_conn = MagicMock()
    mock_cur = AsyncMock()

    # Mock historical database rows
    mock_cur.fetchall.return_value = [
        ("USA", date(2026, 7, 20), 100, 20, 10, 50.0, -0.2),
        ("USA", date(2026, 7, 27), 150, 30, 15, 80.0, -0.5),
    ]
    mock_conn.cursor.return_value.__aenter__.return_value = mock_cur

    features = await extract_country_features_for_date(mock_conn, date(2026, 7, 27), ["USA"])

    assert len(features) == 1
    fv = features[0]
    assert fv.country_code == "USA"
    assert fv.feature_date == date(2026, 7, 27)

    for col in FEATURE_COLUMNS:
        assert col in fv.features
        assert isinstance(fv.features[col], (int, float))

    assert fv.features["conflict_intensity_7d_avg"] >= 0.0
    assert fv.features["sentiment_7d_avg"] >= -1.0
    assert fv.features["sentiment_7d_avg"] <= 1.0
