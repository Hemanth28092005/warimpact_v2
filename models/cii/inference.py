"""Inference pipeline for Country Instability Index (CII)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import joblib  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from psycopg import AsyncConnection

from ingestion.common.logger import get_logger
from models.cii.features import FEATURE_COLUMNS, extract_country_features_for_date
from models.cii.labels import FSI_ANNUAL_BENCHMARKS

logger = get_logger(__name__)

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@dataclass(frozen=True)
class CountryInstabilityPrediction:
    country_code: str
    score_date: date
    cii_score: float  # Bounded in [0.0, 100.0]
    model_version: str
    feature_snapshot: dict[str, float]
    confidence_interval_low: float
    confidence_interval_high: float
    computed_at: datetime


def load_artifacts(artifacts_dir: Path = ARTIFACTS_DIR) -> tuple[Any, Any, dict[str, Any]]:
    """Load trained regressor, classifier, and metadata JSON for active model version."""
    if (artifacts_dir / "active" / "metadata.json").exists():
        target_dir = artifacts_dir / "active"
    elif (artifacts_dir / "metadata.json").exists():
        target_dir = artifacts_dir
    else:
        # Search for versioned subfolders
        subdirs = sorted([d for d in artifacts_dir.iterdir() if d.is_dir() and (d / "metadata.json").exists()], reverse=True)
        if subdirs:
            target_dir = subdirs[0]
        else:
            target_dir = artifacts_dir

    reg_path = target_dir / "regressor_model.joblib"
    cls_path = target_dir / "classifier_model.joblib"
    meta_path = target_dir / "metadata.json"

    if not reg_path.exists() or not cls_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Missing model artifacts in {target_dir}. Run models.cii.train first.")

    regressor = joblib.load(reg_path)
    classifier = joblib.load(cls_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return regressor, classifier, metadata


async def score_country_instability(
    conn: AsyncConnection,
    target_date: date,
    countries: Sequence[str] | None = None,
    artifacts_dir: Path = ARTIFACTS_DIR,
) -> list[CountryInstabilityPrediction]:
    """Calculate CII score [0, 100], 95% CI, escalation probability, and save to DB."""
    if countries is None:
        countries = list(FSI_ANNUAL_BENCHMARKS.keys())

    regressor, classifier, metadata = load_artifacts(artifacts_dir)
    model_version = metadata.get("model_version", "cii-v1.0.0")
    val_rmse = metadata.get("regressor", {}).get("val_rmse", 5.0)

    # 1. Extract feature vectors for target date
    feature_vectors = await extract_country_features_for_date(conn, target_date, countries)
    if not feature_vectors:
        return []

    # 2. Build DataFrame for inference
    rows = []
    c_codes = []
    for fv in feature_vectors:
        c_codes.append(fv.country_code)
        rows.append(fv.features)

    df_X = pd.DataFrame(rows)[FEATURE_COLUMNS]

    # 3. Batch prediction
    raw_scores = regressor.predict(df_X)

    try:
        raw_probs = classifier.predict_proba(df_X)[:, 1]
    except Exception:
        raw_probs = [0.5] * len(df_X)

    computed_at = datetime.now(timezone.utc)
    predictions: list[CountryInstabilityPrediction] = []

    for i, c_code in enumerate(c_codes):
        pred_cii = float(raw_scores[i])
        bounded_cii = max(0.0, min(100.0, round(pred_cii, 2)))

        pred_prob = float(raw_probs[i])
        bounded_prob = max(0.0, min(1.0, round(pred_prob, 4)))

        # 95% prediction interval (empirical residual standard error)
        ci_low = max(0.0, round(bounded_cii - 1.96 * val_rmse, 2))
        ci_high = min(100.0, round(bounded_cii + 1.96 * val_rmse, 2))

        snapshot = {
            **feature_vectors[i].features,
            "escalation_probability": bounded_prob,
        }

        predictions.append(
            CountryInstabilityPrediction(
                country_code=c_code,
                score_date=target_date,
                cii_score=bounded_cii,
                model_version=model_version,
                feature_snapshot=snapshot,
                confidence_interval_low=ci_low,
                confidence_interval_high=ci_high,
                computed_at=computed_at,
            )
        )

    # 4. Upsert to country_instability_index table
    async with conn.cursor() as cur:
        for p in predictions:
            await cur.execute(
                """
                INSERT INTO country_instability_index
                    (country_code, score_date, cii_score, model_version, feature_snapshot,
                     confidence_interval_low, confidence_interval_high, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (country_code, score_date, model_version) DO UPDATE SET
                    cii_score = EXCLUDED.cii_score,
                    feature_snapshot = EXCLUDED.feature_snapshot,
                    confidence_interval_low = EXCLUDED.confidence_interval_low,
                    confidence_interval_high = EXCLUDED.confidence_interval_high,
                    computed_at = EXCLUDED.computed_at
                """,
                (
                    p.country_code,
                    p.score_date,
                    p.cii_score,
                    p.model_version,
                    json.dumps(p.feature_snapshot),
                    p.confidence_interval_low,
                    p.confidence_interval_high,
                    p.computed_at,
                ),
            )
    await conn.commit()

    logger.info(
        "country_instability_scores_computed",
        extra={
            "target_date": str(target_date),
            "model_version": model_version,
            "countries_count": len(predictions),
        },
    )
    return predictions
