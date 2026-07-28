from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.sentiment.signals import (
    CountryDailySignal,
    _compute_normalized_intensity,
)


def test_country_daily_signal_creation() -> None:
    signal = CountryDailySignal(
        country_code="USA",
        signal_date=date(2026, 7, 27),
        event_count=100,
        conflict_event_count=20,
        material_conflict_count=5,
        avg_goldstein=-3.5,
        weighted_conflict_intensity=140.0,
        normalized_conflict_intensity=0.75,
        sentiment_score=-0.45,
        sentiment_sample_size=10,
        sentiment_confidence=0.85,
        computed_at=date(2026, 7, 27),
    )
    assert signal.country_code == "USA"
    assert signal.normalized_conflict_intensity == 0.75
    assert signal.sentiment_score == -0.45


@pytest.mark.asyncio
async def test_compute_normalized_intensity_min_max_scaling() -> None:
    mock_conn = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = [(10.0,), (50.0,)]
    mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)

    norm = await _compute_normalized_intensity(mock_conn, "USA", date(2026, 7, 27), 100.0)

    assert norm == 1.0


@pytest.mark.asyncio
async def test_zero_conflict_country_normalized_intensity_is_zero() -> None:
    mock_conn = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)

    norm = await _compute_normalized_intensity(mock_conn, "USA", date(2026, 7, 27), 0.0)

    assert norm == 0.0
