"""Spike Detector for Phase 4 Cascade / Cross-Stream Correlation.

Formula:
  cii_score > 30-day rolling mean + K * 30-day rolling std

Configuration:
  DEFAULT_K = 2.0 (configurable)

Critical Constraint:
  Queries country_instability_index filtered strictly to a single, active model_version
  to prevent mixing predictions across different trained model iterations.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
import pandas as pd
from psycopg import AsyncConnection
from models.cii.inference import ARTIFACTS_DIR, load_artifacts

# Named constant configuration parameter
DEFAULT_K: float = 2.0
MIN_ROLLING_PERIODS: int = 7
ROLLING_WINDOW_DAYS: int = 30


def load_active_model_version(artifacts_dir: Path = ARTIFACTS_DIR) -> str:
    """Load the model_version identifier of the currently-active CII model."""
    try:
        _, _, metadata = load_artifacts(artifacts_dir)
        return metadata.get("model_version", "cii-v20260730_promoted_live")
    except Exception:
        return "cii-v20260730_promoted_live"


async def detect_country_spikes(
    conn: AsyncConnection,
    k: float = DEFAULT_K,
    model_version: str | None = None,
) -> dict[str, set[date]]:
    """Detect CII spike dates for each country in country_instability_index.

    Args:
        conn: Async PostgreSQL connection.
        k: Multiplier for rolling standard deviation threshold (default 2.0).
        model_version: Model version string to scope query. If None, loads active version.

    Returns:
        Dictionary mapping country code to set of spike dates.
    """
    if model_version is None:
        model_version = load_active_model_version()

    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT country_code, score_date, cii_score
            FROM country_instability_index
            WHERE model_version = %s
            ORDER BY country_code, score_date ASC
            """,
            (model_version,),
        )
        rows = await cur.fetchall()

    if not rows:
        return {}

    df = pd.DataFrame(rows, columns=["country_code", "score_date", "cii_score"])
    df["cii_score"] = df["cii_score"].astype(float)
    df["score_date"] = pd.to_datetime(df["score_date"]).dt.date

    country_spikes: dict[str, set[date]] = {}

    for c_code, group in df.groupby("country_code"):
        group = group.sort_values("score_date").reset_index(drop=True)
        scores = group["cii_score"]

        # Calculate 30-day rolling mean & std
        rolling_mean = scores.rolling(window=ROLLING_WINDOW_DAYS, min_periods=MIN_ROLLING_PERIODS).mean()
        rolling_std = scores.rolling(window=ROLLING_WINDOW_DAYS, min_periods=MIN_ROLLING_PERIODS).std().fillna(0.0)

        threshold = rolling_mean + k * rolling_std
        is_spike = scores > threshold

        spike_dates = set(group.loc[is_spike, "score_date"].tolist())
        country_spikes[c_code] = spike_dates

    return country_spikes
