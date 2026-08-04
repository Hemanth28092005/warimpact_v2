"""Unit tests for Phase 3 CII model training and evaluation."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from models.cii.features import FEATURE_COLUMNS
from models.cii.train import train_and_evaluate_models


def test_train_and_evaluate_models_dual_architecture(tmp_path: Path) -> None:
    # Create synthetic dataset with 50 samples across 5 countries
    dates = [date(2026, 7, 1) + timedelta(days=i) for i in range(10)]
    countries = ["USA", "GBR", "FRA", "RUS", "SYR"]

    rows = []
    np.random.seed(42)
    for d in dates:
        for c in countries:
            base_fsi = 80.0 if c in ["RUS", "SYR"] else 30.0
            feat_dict = {col: float(np.random.uniform(0, 100)) for col in FEATURE_COLUMNS}
            feat_dict.update(
                {
                    "country_code": c,
                    "date": d,
                    "fsi_score": base_fsi + float(np.random.normal(0, 2)),
                    "escalation_label": 1 if c in ["RUS", "SYR"] and np.random.rand() > 0.3 else 0,
                }
            )
            rows.append(feat_dict)

    df_synth = pd.DataFrame(rows)

    metadata, version_dir = train_and_evaluate_models(df_synth, model_version="cii-test-v1", base_artifacts_dir=tmp_path)

    # 1. Regressor Assertions
    assert metadata.regressor.val_rmse >= 0.0
    assert metadata.regressor.val_mae >= 0.0
    assert isinstance(metadata.regressor.beats_baseline, bool)

    # 2. Classifier Assertions (ROC-AUC in [0.0, 1.0])
    assert 0.0 <= metadata.classifier.val_roc_auc <= 1.0
    assert 0.0 <= metadata.classifier.baseline_roc_auc <= 1.0
    assert isinstance(metadata.classifier.beats_baseline, bool)

    # 3. Artifact Files Created in version_dir
    assert (version_dir / "regressor_model.joblib").exists()
    assert (version_dir / "classifier_model.joblib").exists()
    assert (version_dir / "metadata.json").exists()
    assert (version_dir / "feature_importance.png").exists()

    # 4. Feature importances check
    assert len(metadata.feature_importances) == len(FEATURE_COLUMNS)
