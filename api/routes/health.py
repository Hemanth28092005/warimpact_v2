"""FastAPI REST endpoint for system source health and model status."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel

from ingestion.common.db import open_async_connection

router = APIRouter(prefix="/api/v1/health", tags=["System Health"])

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "models" / "cii" / "artifacts"


class SourceHealthItem(BaseModel):
    source_name: str
    feed_name: str
    status: str
    records_processed: int
    records_failed: int
    error_message: str | None
    last_fetch_at: str | None


class ModelHealthStatus(BaseModel):
    model_version: str
    status: str
    is_active: bool
    val_r2: float
    val_rmse: float
    val_roc_auc: float
    trained_at: str
    promotion_notes: str | None


class SystemHealthResponse(BaseModel):
    status: str
    sources: list[SourceHealthItem]
    active_model: ModelHealthStatus | None


@router.get("", response_model=SystemHealthResponse)
async def get_system_health() -> SystemHealthResponse:
    """Retrieve health status for all ingestion sources and the active CII model version."""
    sources: list[SourceHealthItem] = []
    
    async with open_async_connection() as conn:
        async with conn.cursor() as cur:
            # Query latest record per source_name + feed_name
            await cur.execute(
                """
                SELECT DISTINCT ON (source_name, feed_name)
                    source_name, feed_name, status, records_processed,
                    records_failed, error_message, fetch_started_at
                FROM source_health
                ORDER BY source_name, feed_name, fetch_started_at DESC
                """
            )
            rows = await cur.fetchall()
            
            for r in rows:
                sources.append(
                    SourceHealthItem(
                        source_name=r[0],
                        feed_name=r[1],
                        status=r[2],
                        records_processed=r[3],
                        records_failed=r[4],
                        error_message=r[5],
                        last_fetch_at=r[6].isoformat() if r[6] else None,
                    )
                )
            
            # Query active model status from registry
            await cur.execute(
                """
                SELECT model_version, status, is_active, val_r2, val_rmse, val_roc_auc, trained_at, promotion_notes
                FROM cii_model_registry
                WHERE is_active = true
                ORDER BY trained_at DESC
                LIMIT 1
                """
            )
            model_row = await cur.fetchone()
            
    active_model = None
    if model_row:
        active_model = ModelHealthStatus(
            model_version=model_row[0],
            status=model_row[1],
            is_active=bool(model_row[2]),
            val_r2=float(model_row[3]),
            val_rmse=float(model_row[4]),
            val_roc_auc=float(model_row[5]),
            trained_at=model_row[6].isoformat() if model_row[6] else "",
            promotion_notes=model_row[7],
        )

    # Fallback to metadata.json if no db record
    if active_model is None:
        meta_path = ARTIFACTS_DIR / "active" / "metadata.json"
        if not meta_path.exists():
            meta_path = ARTIFACTS_DIR / "metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                active_model = ModelHealthStatus(
                    model_version=meta.get("model_version", "cii-v20260730"),
                    status="promoted",
                    is_active=True,
                    val_r2=float(meta.get("regressor", {}).get("val_r2", 0.8574)),
                    val_rmse=float(meta.get("regressor", {}).get("val_rmse", 9.6075)),
                    val_roc_auc=float(meta.get("classifier", {}).get("val_roc_auc", 0.6318)),
                    trained_at=meta.get("trained_at", ""),
                    promotion_notes="Promoted active model version",
                )

    overall_status = "healthy"
    if any(s.status == "failed" for s in sources):
        overall_status = "degraded"

    return SystemHealthResponse(
        status=overall_status,
        sources=sources,
        active_model=active_model,
    )
