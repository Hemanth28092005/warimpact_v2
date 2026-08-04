"""Model registry and regression guardrail management for Country Instability Index (CII)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from psycopg import AsyncConnection, Connection

from ingestion.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GuardrailResult:
    is_promoted: bool
    status: str  # 'promoted', 'held_back', 'initial'
    reason: str
    active_version: str | None
    new_version: str
    active_r2: float | None
    new_r2: float
    active_auc: float | None
    new_auc: float


def evaluate_regression_guardrail(
    new_metadata: dict[str, Any],
    active_metadata: dict[str, Any] | None,
    r2_decline_threshold: float = 0.15,
    auc_drop_margin: float = 0.05,
) -> GuardrailResult:
    """Evaluate whether newly trained model passes regression guardrails relative to active model."""
    new_version = new_metadata["model_version"]
    new_r2 = float(new_metadata["regressor"]["val_r2"])
    new_auc = float(new_metadata["classifier"]["val_roc_auc"])

    if not active_metadata:
        return GuardrailResult(
            is_promoted=True,
            status="initial",
            reason="Initial model version established as active baseline.",
            active_version=None,
            new_version=new_version,
            active_r2=None,
            new_r2=new_r2,
            active_auc=None,
            new_auc=new_auc,
        )

    active_version = active_metadata.get("model_version", "unknown")
    active_r2 = float(active_metadata.get("regressor", {}).get("val_r2", 0.0))
    active_auc = float(active_metadata.get("classifier", {}).get("val_roc_auc", 0.5))

    reasons = []
    is_regression = False

    # 1. Regressor R² Check (15% relative decline threshold)
    if active_r2 > 0:
        r2_decline = (active_r2 - new_r2) / active_r2
        if r2_decline > r2_decline_threshold:
            is_regression = True
            reasons.append(
                f"Regressor R² suffered relative decline of {r2_decline * 100:.2f}% "
                f"(new: {new_r2:.4f} vs active: {active_r2:.4f}, exceeds {r2_decline_threshold * 100:.1f}% threshold)"
            )

    # 2. Classifier ROC-AUC Check (0.05 drop margin threshold)
    auc_drop = active_auc - new_auc
    if auc_drop > auc_drop_margin:
        is_regression = True
        reasons.append(
            f"Classifier ROC-AUC dropped by {auc_drop:.4f} "
            f"(new: {new_auc:.4f} vs active: {active_auc:.4f}, exceeds {auc_drop_margin:.2f} margin)"
        )

    if is_regression:
        combined_reason = "; ".join(reasons)
        logger.warning(
            "cii_retrain_regression_detected",
            extra={
                "new_version": new_version,
                "active_version": active_version,
                "new_r2": new_r2,
                "active_r2": active_r2,
                "new_auc": new_auc,
                "active_auc": active_auc,
                "reason": combined_reason,
            },
        )
        return GuardrailResult(
            is_promoted=False,
            status="held_back",
            reason=f"Regression detected: {combined_reason}",
            active_version=active_version,
            new_version=new_version,
            active_r2=active_r2,
            new_r2=new_r2,
            active_auc=active_auc,
            new_auc=new_auc,
        )

    return GuardrailResult(
        is_promoted=True,
        status="promoted",
        reason=f"Passed regression guardrail (new R²: {new_r2:.4f} vs active: {active_r2:.4f}, new AUC: {new_auc:.4f} vs active: {active_auc:.4f}).",
        active_version=active_version,
        new_version=new_version,
        active_r2=active_r2,
        new_r2=new_r2,
        active_auc=active_auc,
        new_auc=new_auc,
    )


async def get_active_model_record(conn: AsyncConnection) -> dict[str, Any] | None:
    """Fetch metadata of currently active model from cii_model_registry."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT model_version, metadata_snapshot
            FROM cii_model_registry
            WHERE is_active = TRUE
            ORDER BY trained_at DESC
            LIMIT 1
            """
        )
        row = await cur.fetchone()
        if not row:
            return None
        return dict(row[1])


def get_active_model_record_sync(conn: Connection) -> dict[str, Any] | None:
    """Fetch metadata of currently active model synchronously."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT model_version, metadata_snapshot
            FROM cii_model_registry
            WHERE is_active = TRUE
            ORDER BY trained_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row[1])


async def record_trained_model(
    conn: AsyncConnection,
    metadata: dict[str, Any],
    r2_decline_threshold: float = 0.15,
    auc_drop_margin: float = 0.05,
) -> GuardrailResult:
    """Evaluate guardrail and record trained model in cii_model_registry."""
    active_meta = await get_active_model_record(conn)
    guardrail = evaluate_regression_guardrail(
        metadata, active_meta, r2_decline_threshold=r2_decline_threshold, auc_drop_margin=auc_drop_margin
    )

    m_ver = metadata["model_version"]
    trained_at = datetime.fromisoformat(metadata["trained_at"])
    tr_start = date.fromisoformat(metadata["train_date_range"][0])
    tr_end = date.fromisoformat(metadata["train_date_range"][1])
    val_start = date.fromisoformat(metadata["val_date_range"][0])
    val_end = date.fromisoformat(metadata["val_date_range"][1])

    async with conn.cursor() as cur:
        if guardrail.is_promoted:
            # Deactivate previous active models
            await cur.execute("UPDATE cii_model_registry SET is_active = FALSE WHERE is_active = TRUE")

        await cur.execute(
            """
            INSERT INTO cii_model_registry (
                model_version, trained_at, train_date_start, train_date_end,
                val_date_start, val_date_end, in_scope_countries_count, train_samples_count,
                val_samples_count, regressor_type, val_rmse, val_mae, val_r2,
                baseline_rmse, classifier_type, val_roc_auc, baseline_roc_auc,
                status, is_active, promotion_notes, metadata_snapshot
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (model_version) DO UPDATE SET
                status = EXCLUDED.status,
                is_active = EXCLUDED.is_active,
                promotion_notes = EXCLUDED.promotion_notes,
                metadata_snapshot = EXCLUDED.metadata_snapshot
            """,
            (
                m_ver,
                trained_at,
                tr_start,
                tr_end,
                val_start,
                val_end,
                int(metadata["in_scope_countries_count"]),
                int(metadata["train_samples_count"]),
                int(metadata["val_samples_count"]),
                str(metadata["regressor"]["model_type"]),
                float(metadata["regressor"]["val_rmse"]),
                float(metadata["regressor"]["val_mae"]),
                float(metadata["regressor"]["val_r2"]),
                float(metadata["regressor"]["baseline_rmse"]),
                str(metadata["classifier"]["model_type"]),
                float(metadata["classifier"]["val_roc_auc"]),
                float(metadata["classifier"]["baseline_roc_auc"]),
                guardrail.status,
                guardrail.is_promoted,
                guardrail.reason,
                json.dumps(metadata),
            ),
        )
    await conn.commit()

    logger.info(
        "cii_model_registered",
        extra={
            "model_version": m_ver,
            "status": guardrail.status,
            "is_active": guardrail.is_promoted,
            "reason": guardrail.reason,
        },
    )
    return guardrail
