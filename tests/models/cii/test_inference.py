"""Unit tests for Phase 3 CII inference."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cii.inference import score_country_instability
from models.cii.train import train_and_evaluate_models
from tests.models.cii.test_train import test_train_and_evaluate_models_dual_architecture


@pytest.mark.asyncio
async def test_score_country_instability(tmp_path: Path) -> None:
    # Train artifacts in tmp_path first
    test_train_and_evaluate_models_dual_architecture(tmp_path)

    mock_conn = MagicMock()
    mock_cur = AsyncMock()

    mock_cur.fetchall.return_value = [
        ("USA", date(2026, 7, 27), 100, 20, 10, 50.0, -0.2),
    ]
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor.return_value = mock_cm
    mock_conn.commit = AsyncMock()

    predictions = await score_country_instability(
        mock_conn,
        date(2026, 7, 27),
        countries=["USA"],
        artifacts_dir=tmp_path,
    )

    assert len(predictions) == 1
    p = predictions[0]
    assert p.country_code == "USA"
    assert 0.0 <= p.cii_score <= 100.0
    assert 0.0 <= p.confidence_interval_low <= p.confidence_interval_high <= 100.0
    assert "escalation_probability" in p.feature_snapshot
    assert 0.0 <= p.feature_snapshot["escalation_probability"] <= 1.0
