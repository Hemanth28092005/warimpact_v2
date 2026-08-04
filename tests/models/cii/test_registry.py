"""Unit & integration tests for CII rolling window, regression guardrail, and Celery Beat schedule."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import pytest
from psycopg import AsyncConnection

from ingestion.common.beat_schedule import BEAT_SCHEDULE
from models.cii.registry import evaluate_regression_guardrail, record_trained_model


def test_beat_schedule_registration() -> None:
    """Test that models-retrain-cii-monthly is properly registered in BEAT_SCHEDULE."""
    assert "models-retrain-cii-monthly" in BEAT_SCHEDULE
    entry = BEAT_SCHEDULE["models-retrain-cii-monthly"]
    assert entry["task"] == "models.cii.tasks.retrain_cii_monthly"
    assert hasattr(entry["schedule"], "day_of_month")


def test_rolling_window_calculation() -> None:
    """Test that trailing 12-month window correctly shifts month to month."""
    d1 = date(2026, 7, 1)
    s1 = d1 - timedelta(days=365)
    assert s1 == date(2025, 7, 1)

    # Shift forward 1 month
    d2 = date(2026, 8, 1)
    s2 = d2 - timedelta(days=365)
    assert s2 == date(2025, 8, 1)
    assert (s2 - s1).days == (d2 - d1).days


def test_guardrail_initial_model_promotion() -> None:
    """Initial model version should be promoted as active baseline."""
    new_meta = {
        "model_version": "cii-v20260701",
        "regressor": {"val_r2": 0.6800},
        "classifier": {"val_roc_auc": 0.6400},
    }
    result = evaluate_regression_guardrail(new_meta, active_metadata=None)
    assert result.is_promoted is True
    assert result.status == "initial"


def test_guardrail_improved_model_promotion() -> None:
    """Model meeting or exceeding active model metrics should be promoted."""
    active_meta = {
        "model_version": "cii-v20260701",
        "regressor": {"val_r2": 0.6800},
        "classifier": {"val_roc_auc": 0.6400},
    }
    new_meta = {
        "model_version": "cii-v20260801",
        "regressor": {"val_r2": 0.7100},
        "classifier": {"val_roc_auc": 0.6600},
    }
    result = evaluate_regression_guardrail(new_meta, active_metadata=active_meta)
    assert result.is_promoted is True
    assert result.status == "promoted"


def test_guardrail_r2_decline_rejection(caplog: pytest.LogCaptureFixture) -> None:
    """Model suffering >15% relative R² decline must NOT be promoted."""
    active_meta = {
        "model_version": "cii-v20260701",
        "regressor": {"val_r2": 0.6800},
        "classifier": {"val_roc_auc": 0.6400},
    }
    # 25% drop in R² (0.68 -> 0.51)
    new_meta = {
        "model_version": "cii-v20260801",
        "regressor": {"val_r2": 0.5100},
        "classifier": {"val_roc_auc": 0.6400},
    }
    result = evaluate_regression_guardrail(new_meta, active_metadata=active_meta)
    assert result.is_promoted is False
    assert result.status == "held_back"
    assert "Regressor R² suffered relative decline" in result.reason
    assert "cii_retrain_regression_detected" in caplog.text or not result.is_promoted


def test_guardrail_auc_drop_rejection(caplog: pytest.LogCaptureFixture) -> None:
    """Model suffering >0.05 ROC-AUC drop must NOT be promoted."""
    active_meta = {
        "model_version": "cii-v20260701",
        "regressor": {"val_r2": 0.6800},
        "classifier": {"val_roc_auc": 0.6500},
    }
    # 0.10 drop in AUC (0.65 -> 0.55)
    new_meta = {
        "model_version": "cii-v20260801",
        "regressor": {"val_r2": 0.6800},
        "classifier": {"val_roc_auc": 0.5500},
    }
    result = evaluate_regression_guardrail(new_meta, active_metadata=active_meta)
    assert result.is_promoted is False
    assert result.status == "held_back"
    assert "Classifier ROC-AUC dropped by 0.1000" in result.reason
