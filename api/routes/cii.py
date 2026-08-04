"""FastAPI router for Phase 3 Country Instability Index (CII) endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ingestion.common.db import open_async_connection

router = APIRouter(prefix="/api/v1/cii", tags=["Country Instability Index"])

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "models" / "cii" / "artifacts"


class CIIScoreResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    country_code: str
    score_date: str
    cii_score: float = Field(..., ge=0.0, le=100.0)
    model_version: str
    confidence_interval_low: float = Field(..., ge=0.0, le=100.0)
    confidence_interval_high: float = Field(..., ge=0.0, le=100.0)
    feature_snapshot: dict[str, Any]
    computed_at: str


class ModelInfoResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    trained_at: str
    in_scope_countries_count: int
    train_samples_count: int
    val_samples_count: int
    train_date_range: list[str]
    val_date_range: list[str]
    regressor: dict[str, Any]
    classifier: dict[str, Any]
    confidence_interval_method: str
    feature_importances: dict[str, float]
    label_proxy_caveats: str


@router.get("/latest", response_model=list[CIIScoreResponse])
async def get_latest_cii_scores() -> list[dict[str, Any]]:
    """Retrieve the most recent CII scores for all in-scope countries."""
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT ON (country_code)
                    country_code, score_date, cii_score, model_version,
                    confidence_interval_low, confidence_interval_high,
                    feature_snapshot, computed_at
                FROM country_instability_index
                ORDER BY country_code, score_date DESC
                """
            )
            rows = await cur.fetchall()

    results = []
    for r in rows:
        snapshot = r[6] if isinstance(r[6], dict) else json.loads(r[6])
        computed_at_str = r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7])
        results.append(
            {
                "country_code": r[0],
                "score_date": str(r[1]),
                "cii_score": float(r[2]),
                "model_version": r[3],
                "confidence_interval_low": float(r[4]),
                "confidence_interval_high": float(r[5]),
                "feature_snapshot": snapshot,
                "computed_at": computed_at_str,
            }
        )
    return results


@router.get("/model-info", response_model=ModelInfoResponse)
async def get_model_info() -> dict[str, Any]:
    """Retrieve active model version, evaluation metrics, feature importances, and proxy caveats."""
    meta_path = ARTIFACTS_DIR / "active" / "metadata.json"
    if not meta_path.exists():
        meta_path = ARTIFACTS_DIR / "metadata.json"

    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Model metadata not found. Run model training first.")

    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return cast(dict[str, Any], data)


@router.get("/registry")
async def get_model_registry_history() -> list[dict[str, Any]]:
    """Retrieve historical model retrain runs, evaluation metrics, status (promoted/held_back), and guardrail notes."""
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT model_version, trained_at, train_date_start, train_date_end,
                       val_date_start, val_date_end, regressor_type, val_rmse, val_mae, val_r2,
                       classifier_type, val_roc_auc, status, is_active, promotion_notes
                FROM cii_model_registry
                ORDER BY trained_at DESC
                """
            )
            rows = await cur.fetchall()

    results = []
    for r in rows:
        results.append(
            {
                "model_version": r[0],
                "trained_at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                "train_date_range": [str(r[2]), str(r[3])],
                "val_date_range": [str(r[4]), str(r[5])],
                "regressor_type": r[6],
                "val_rmse": float(r[7]),
                "val_mae": float(r[8]),
                "val_r2": float(r[9]),
                "classifier_type": r[10],
                "val_roc_auc": float(r[11]),
                "status": r[12],
                "is_active": bool(r[13]),
                "promotion_notes": r[14],
            }
        )
    return results


@router.get("/{country_code}", response_model=list[CIIScoreResponse])
async def get_country_cii_history(
    country_code: str,
    limit: int = Query(default=30, ge=1, le=365),
) -> list[dict[str, Any]]:
    """Retrieve historical CII scores and snapshots for a specific country."""
    c_upper = country_code.upper()
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT country_code, score_date, cii_score, model_version,
                       confidence_interval_low, confidence_interval_high,
                       feature_snapshot, computed_at
                FROM country_instability_index
                WHERE country_code = %s
                ORDER BY score_date DESC
                LIMIT %s
                """,
                (c_upper, limit),
            )
            rows = await cur.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No CII scores found for country '{c_upper}'.",
        )

    results = []
    for r in rows:
        snapshot = r[6] if isinstance(r[6], dict) else json.loads(r[6])
        computed_at_str = r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7])
        results.append(
            {
                "country_code": r[0],
                "score_date": str(r[1]),
                "cii_score": float(r[2]),
                "model_version": r[3],
                "confidence_interval_low": float(r[4]),
                "confidence_interval_high": float(r[5]),
                "feature_snapshot": snapshot,
                "computed_at": computed_at_str,
            }
        )
    return results
