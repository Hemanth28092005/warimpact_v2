"""Unit tests for Fragile States Index proxy labels."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cii.labels import get_interpolated_fsi_score, seed_training_labels


def test_get_interpolated_fsi_score_bounds() -> None:
    score_usa = get_interpolated_fsi_score("USA", date(2026, 7, 27))
    assert 0.0 <= score_usa <= 100.0

    score_syr = get_interpolated_fsi_score("SYR", date(2026, 7, 27))
    assert 0.0 <= score_syr <= 100.0
    assert score_syr > score_usa  # Syria higher instability than USA

    score_unknown = get_interpolated_fsi_score("XYZ", date(2026, 7, 27))
    assert score_unknown == 50.0


@pytest.mark.asyncio
async def test_seed_training_labels_executes() -> None:
    mock_conn = MagicMock()
    mock_cur = AsyncMock()

    mock_cur.fetchall.return_value = [
        ("USA", date(2026, 7, 20), 50.0),
        ("USA", date(2026, 7, 27), 80.0),
    ]
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor.return_value = mock_cm
    mock_conn.commit = AsyncMock()

    inserted = await seed_training_labels(mock_conn, [date(2026, 7, 27)], ["USA"])
    assert inserted == 1
