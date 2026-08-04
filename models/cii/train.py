"""Dual-model training and selection pipeline for Country Instability Index (CII)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from lightgbm import LGBMClassifier, LGBMRegressor
from psycopg import AsyncConnection
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, roc_auc_score  # type: ignore[import-untyped]
from xgboost import XGBClassifier, XGBRegressor

from ingestion.common.db import open_async_connection
from ingestion.common.logger import get_logger
from models.cii.features import FEATURE_COLUMNS, extract_country_features_for_date
from models.cii.labels import FSI_ANNUAL_BENCHMARKS, seed_training_labels

logger = get_logger(__name__)

import shutil
from models.cii.registry import GuardrailResult, record_trained_model

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@dataclass
class RegressorMetrics:
    model_type: str
    val_rmse: float
    val_mae: float
    val_r2: float
    baseline_rmse: float
    beats_baseline: bool


@dataclass
class ClassifierMetrics:
    model_type: str
    val_roc_auc: float
    baseline_roc_auc: float
    beats_baseline: bool


@dataclass
class ModelMetadata:
    model_version: str
    trained_at: str
    in_scope_countries_count: int
    train_samples_count: int
    val_samples_count: int
    train_date_range: list[str]
    val_date_range: list[str]
    regressor: RegressorMetrics
    classifier: ClassifierMetrics
    confidence_interval_method: str
    feature_importances: dict[str, float]
    label_proxy_caveats: str


async def prepare_training_dataset(
    conn: AsyncConnection,
    target_dates: list[date],
    countries: list[str],
) -> pd.DataFrame:
    """Extract features and labels across dates and countries into a pandas DataFrame."""
    await seed_training_labels(conn, target_dates, countries)

    rows_data = []

    for d in target_dates:
        feature_vectors = await extract_country_features_for_date(conn, d, countries)
        feat_map = {fv.country_code: fv.features for fv in feature_vectors}

        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT country_code, fsi_score, escalation_label
                FROM cii_training_labels
                WHERE label_date = %s AND country_code = ANY(%s)
                """,
                (d, countries),
            )
            label_rows = await cur.fetchall()

        for c_code, fsi, esc in label_rows:
            if c_code in feat_map:
                row_dict = {
                    "country_code": c_code,
                    "date": d,
                    "fsi_score": float(fsi),
                    "escalation_label": int(esc),
                    **feat_map[c_code],
                }
                rows_data.append(row_dict)

    df = pd.DataFrame(rows_data)
    return df


def train_and_evaluate_models(
    df: pd.DataFrame,
    model_version: str = "cii-v1.0.0",
    base_artifacts_dir: Path = ARTIFACTS_DIR,
) -> tuple[ModelMetadata, Path]:
    """Train XGBoost & LightGBM regressors and classifiers, select best models, and save artifacts under versioned directory."""
    version_dir = base_artifacts_dir / model_version
    version_dir.mkdir(parents=True, exist_ok=True)

    # Sort temporally to avoid lookahead bias
    df = df.sort_values("date").reset_index(drop=True)

    # Temporal split (80% train, 20% val)
    split_idx = int(len(df) * 0.8)
    if split_idx == 0 or split_idx == len(df):
        split_idx = max(1, len(df) - 1)

    df_train = df.iloc[:split_idx]
    df_val = df.iloc[split_idx:]

    X_train = df_train[FEATURE_COLUMNS]
    y_reg_train = df_train["fsi_score"]
    y_cls_train = df_train["escalation_label"]

    X_val = df_val[FEATURE_COLUMNS]
    y_reg_val = df_val["fsi_score"]
    y_cls_val = df_val["escalation_label"]

    # ---------------------------------------------------------
    # 1. Regressor Evaluation (FSI Continuous Prediction)
    # ---------------------------------------------------------
    baseline_mean = y_reg_train.mean()
    baseline_reg_preds = np.full_like(y_reg_val, fill_value=baseline_mean)
    baseline_rmse = float(np.sqrt(mean_squared_error(y_reg_val, baseline_reg_preds)))

    xgb_reg = XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42)
    xgb_reg.fit(X_train, y_reg_train)
    xgb_reg_preds = xgb_reg.predict(X_val)
    xgb_rmse = float(np.sqrt(mean_squared_error(y_reg_val, xgb_reg_preds)))

    lgb_reg = LGBMRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, verbose=-1)
    lgb_reg.fit(X_train, y_reg_train)
    lgb_reg_preds = lgb_reg.predict(X_val)
    lgb_rmse = float(np.sqrt(mean_squared_error(y_reg_val, lgb_reg_preds)))

    if lgb_rmse < xgb_rmse:
        best_regressor = lgb_reg
        best_reg_name = "LightGBM Regressor"
        best_reg_preds = lgb_reg_preds
        best_reg_rmse = lgb_rmse
    else:
        best_regressor = xgb_reg
        best_reg_name = "XGBoost Regressor"
        best_reg_preds = xgb_reg_preds
        best_reg_rmse = xgb_rmse

    val_mae = float(mean_absolute_error(y_reg_val, best_reg_preds))
    val_r2 = float(r2_score(y_reg_val, best_reg_preds)) if len(y_reg_val) > 1 else 0.0

    reg_metrics = RegressorMetrics(
        model_type=best_reg_name,
        val_rmse=round(best_reg_rmse, 4),
        val_mae=round(val_mae, 4),
        val_r2=round(val_r2, 4),
        baseline_rmse=round(baseline_rmse, 4),
        beats_baseline=bool(best_reg_rmse < baseline_rmse),
    )

    # ---------------------------------------------------------
    # 2. Classifier Evaluation (14-day Escalation 0/1)
    # ---------------------------------------------------------
    has_positives = (y_cls_train.nunique() > 1) and (y_cls_val.nunique() > 1)
    baseline_auc = 0.50

    if has_positives:
        xgb_cls = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42)
        xgb_cls.fit(X_train, y_cls_train)
        xgb_cls_probs = xgb_cls.predict_proba(X_val)[:, 1]
        xgb_auc = float(roc_auc_score(y_cls_val, xgb_cls_probs))

        lgb_cls = LGBMClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42, verbose=-1)
        lgb_cls.fit(X_train, y_cls_train)
        lgb_cls_probs = lgb_cls.predict_proba(X_val)[:, 1]  # type: ignore[call-overload]
        lgb_auc = float(roc_auc_score(y_cls_val, lgb_cls_probs))

        if lgb_auc > xgb_auc:
            best_classifier = lgb_cls
            best_cls_name = "LightGBM Classifier"
            best_auc = lgb_auc
        else:
            best_classifier = xgb_cls
            best_cls_name = "XGBoost Classifier"
            best_auc = xgb_auc
    else:
        best_classifier = XGBClassifier(n_estimators=10, max_depth=2, random_state=42)
        best_classifier.fit(X_train, y_cls_train)
        best_cls_name = "XGBoost Classifier (Fallback)"
        best_auc = 0.50

    cls_metrics = ClassifierMetrics(
        model_type=best_cls_name,
        val_roc_auc=round(best_auc, 4),
        baseline_roc_auc=round(baseline_auc, 4),
        beats_baseline=bool(best_auc > baseline_auc),
    )

    # ---------------------------------------------------------
    # 3. Feature Importance Extraction & Plotting
    # ---------------------------------------------------------
    raw_importances = best_regressor.feature_importances_
    norm_importances = raw_importances / (raw_importances.sum() + 1e-8)
    feat_imp_map = {
        col: round(float(imp), 4) for col, imp in zip(FEATURE_COLUMNS, norm_importances)
    }

    plt.figure(figsize=(10, 6))
    sorted_feats = sorted(feat_imp_map.items(), key=lambda x: x[1], reverse=True)
    names = [x[0] for x in sorted_feats]
    values = [x[1] for x in sorted_feats]
    plt.barh(names[::-1], values[::-1], color="#2b5c8f")
    plt.title(f"CII Feature Importance ({best_reg_name})")
    plt.xlabel("Relative Importance Weight")
    plt.tight_layout()
    plot_path = version_dir / "feature_importance.png"
    plt.savefig(plot_path, dpi=150)
    plt.close()

    # ---------------------------------------------------------
    # 4. Save Artifacts & Metadata JSON in version_dir
    # ---------------------------------------------------------
    joblib.dump(best_regressor, version_dir / "regressor_model.joblib")
    joblib.dump(best_classifier, version_dir / "classifier_model.joblib")

    metadata = ModelMetadata(
        model_version=model_version,
        trained_at=pd.Timestamp.now(tz="UTC").isoformat(),
        in_scope_countries_count=len(df["country_code"].unique()),
        train_samples_count=len(df_train),
        val_samples_count=len(df_val),
        train_date_range=[str(df_train["date"].min()), str(df_train["date"].max())],
        val_date_range=[str(df_val["date"].min()), str(df_val["date"].max())],
        regressor=reg_metrics,
        classifier=cls_metrics,
        confidence_interval_method="empirical_residual_std_error_95pct",
        feature_importances=feat_imp_map,
        label_proxy_caveats=(
            "Annual FSI total scores linearly interpolated to daily frequency "
            "as a long-term stability proxy target, not daily ground truth. "
            "Historical training signals use composite formula (0.4*tone_norm + 0.4*goldstein_norm + 0.2*quad_signed) "
            "with confidence=0.65 (no article scraping performed for backfill dates), whereas live production "
            "scoring uses real RoBERTa text + AvgTone fallback."
        ),
    )

    metadata_path = version_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(asdict(metadata), f, indent=2)

    logger.info(
        "model_training_completed",
        extra={
            "model_version": model_version,
            "regressor": best_reg_name,
            "val_rmse": best_reg_rmse,
            "classifier": best_cls_name,
            "val_roc_auc": best_auc,
        },
    )
    return metadata, version_dir


def update_active_artifacts(version_dir: Path, base_artifacts_dir: Path = ARTIFACTS_DIR) -> None:
    """Copy promoted version artifacts to active/ directory and root artifacts dir for backward compatibility."""
    active_dir = base_artifacts_dir / "active"
    active_dir.mkdir(parents=True, exist_ok=True)

    for item in version_dir.glob("*"):
        if item.is_file():
            shutil.copy2(item, active_dir / item.name)
            shutil.copy2(item, base_artifacts_dir / item.name)


async def run_training_pipeline(
    target_end_date: date | None = None,
    model_version: str | None = None,
    r2_decline_threshold: float = 0.15,
    auc_drop_margin: float = 0.05,
) -> tuple[ModelMetadata, GuardrailResult]:
    """Execute complete rolling trailing-12-month training pipeline with regression guardrails."""
    countries = list(FSI_ANNUAL_BENCHMARKS.keys())
    # Default to yesterday so country_daily_signals is fully ready and completed for all countries
    end_d = target_end_date or (date.today() - timedelta(days=1))
    start_d = end_d - timedelta(days=365)

    if model_version is None:
        model_version = f"cii-v{end_d.strftime('%Y%m%d')}"

    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT signal_date
                FROM country_daily_signals
                WHERE signal_date >= %s AND signal_date <= %s
                ORDER BY signal_date ASC
                """,
                (start_d, end_d),
            )
            rows = await cur.fetchall()
            target_dates = [r[0] for r in rows]

        if not target_dates:
            target_dates = [end_d - timedelta(days=i) for i in range(365, -1, -1)]

        df = await prepare_training_dataset(conn, target_dates, countries)
        metadata, version_dir = train_and_evaluate_models(df, model_version=model_version)

        guardrail = await record_trained_model(
            conn,
            asdict(metadata),
            r2_decline_threshold=r2_decline_threshold,
            auc_drop_margin=auc_drop_margin,
        )

        if guardrail.is_promoted:
            update_active_artifacts(version_dir, ARTIFACTS_DIR)

    return metadata, guardrail


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_training_pipeline())
