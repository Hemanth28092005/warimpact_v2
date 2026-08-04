"""Feature engineering for Country Instability Index (CII), including Phase 5 Trade Exposure Features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from psycopg import AsyncConnection

from ingestion.common.logger import get_logger

logger = get_logger(__name__)

FEATURE_COLUMNS = [
    "conflict_intensity_7d_avg",
    "conflict_intensity_30d_avg",
    "sentiment_7d_avg",
    "sentiment_30d_avg",
    "intensity_7d_delta",
    "intensity_30d_std",
    "volume_trend_7d_30d_ratio",
    "event_count_7d_avg",
    "event_count_30d_avg",
    "material_conflict_30d_sum",
    "trade_concentration",
]


@dataclass(frozen=True)
class CountryFeatureVector:
    country_code: str
    feature_date: date
    features: dict[str, float]


async def _fetch_trade_metrics(
    conn: AsyncConnection,
    target_date: date,
    countries: Sequence[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Query bilateral_trade and active CII partner scores to compute trade_concentration and conflict_partner_exposure."""
    trade_concentration: dict[str, float] = {c: 0.0500 for c in countries}
    conflict_partner_exposure: dict[str, float] = {c: 65.0000 for c in countries}

    try:
        # 1. Fetch bilateral_trade for 2023 across all partners
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT reporter_country, partner_country, trade_value_usd
                FROM bilateral_trade
                WHERE year = 2023 AND trade_flow = 'total'
                """
            )
            trade_rows = await cur.fetchall()

        # 2. Fetch active model's CII scores for in-scope partners on target_date
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT country_code, cii_score
                FROM country_instability_index
                WHERE score_date = %s AND model_version = 'cii-v20260730_promoted_live'
                """,
                (target_date,),
            )
            cii_rows = await cur.fetchall()

        partner_cii_map = {}
        for r in cii_rows:
            if len(r) >= 2 and r[0] is not None and r[1] is not None:
                try:
                    partner_cii_map[str(r[0])] = float(r[1])
                except (ValueError, TypeError):
                    pass

        reporter_trades: dict[str, list[tuple[str, float]]] = {c: [] for c in countries}
        for r in trade_rows:
            if len(r) >= 3 and r[0] is not None and r[1] is not None:
                try:
                    rep, partner, val_usd = str(r[0]), str(r[1]), float(r[2])
                    if rep in reporter_trades:
                        reporter_trades[rep].append((partner, val_usd))
                except (ValueError, TypeError):
                    pass

        for c_code in countries:
            pairs = reporter_trades.get(c_code, [])
            total_global_val = sum(v for _, v in pairs)

            if total_global_val > 0:
                hhi = sum(((v / total_global_val) * 100.0) ** 2 for _, v in pairs)
                trade_concentration[c_code] = round(hhi / 10000.0, 4)

            in_scope_pairs = [(p, v) for p, v in pairs if p in partner_cii_map]
            total_in_scope_val = sum(v for _, v in in_scope_pairs)

            if total_in_scope_val > 0:
                weighted_cii = sum(v * partner_cii_map[p] for p, v in in_scope_pairs) / total_in_scope_val
                conflict_partner_exposure[c_code] = round(weighted_cii, 4)
            elif partner_cii_map:
                avg_partner_cii = float(np.mean(list(partner_cii_map.values())))
                conflict_partner_exposure[c_code] = round(avg_partner_cii, 4)

    except Exception as exc:
        logger.warning("trade_metrics_fetch_fallback", extra={"error": str(exc)})

    return trade_concentration, conflict_partner_exposure


async def extract_country_features_for_date(
    conn: AsyncConnection,
    target_date: date,
    countries: Sequence[str],
) -> list[CountryFeatureVector]:
    """Extract rolling features and trade exposure features for in-scope countries for a target date."""
    start_date = target_date - timedelta(days=60)

    # 1. Query historical country_daily_signals for 60-day window
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT country_code, signal_date, event_count, conflict_event_count,
                   material_conflict_count, weighted_conflict_intensity, sentiment_score
            FROM country_daily_signals
            WHERE signal_date >= %s AND signal_date <= %s AND country_code = ANY(%s)
            ORDER BY country_code, signal_date
            """,
            (start_date, target_date, list(countries)),
        )
        rows = await cur.fetchall()

    records = []
    for r in rows:
        records.append(
            {
                "country_code": r[0],
                "signal_date": r[1],
                "event_count": float(r[2]),
                "conflict_event_count": float(r[3]),
                "material_conflict_count": float(r[4]),
                "weighted_conflict_intensity": float(r[5]),
                "sentiment_score": float(r[6]),
            }
        )

    df_raw = pd.DataFrame(records)

    # Generate full date grid for each in-scope country
    all_dates = [start_date + timedelta(days=i) for i in range((target_date - start_date).days + 1)]
    grid_rows = []
    for c in countries:
        for d in all_dates:
            grid_rows.append({"country_code": c, "signal_date": d})
    df_grid = pd.DataFrame(grid_rows)

    if not df_raw.empty:
        df_merged = pd.merge(df_grid, df_raw, on=["country_code", "signal_date"], how="left")
    else:
        df_merged = df_grid
        for col in [
            "event_count",
            "conflict_event_count",
            "material_conflict_count",
            "weighted_conflict_intensity",
            "sentiment_score",
        ]:
            df_merged[col] = np.nan

    # Forward-fill missing dates up to 3 consecutive days per country, remaining filled with 0.0
    df_merged = df_merged.sort_values(["country_code", "signal_date"])
    for col in [
        "event_count",
        "conflict_event_count",
        "material_conflict_count",
        "weighted_conflict_intensity",
        "sentiment_score",
    ]:
        df_merged[col] = (
            df_merged.groupby("country_code")[col]
            .transform(lambda s: s.ffill(limit=3))
            .fillna(0.0)
        )

    # 2. Fetch trade features
    trade_conc_map, partner_exp_map = await _fetch_trade_metrics(conn, target_date, countries)

    # 3. Compute rolling metrics per country
    feature_vectors: list[CountryFeatureVector] = []

    for c, group in df_merged.groupby("country_code"):
        c_str = str(c)
        group = group.sort_values("signal_date").reset_index(drop=True)
        target_idx_list = group.index[group["signal_date"] == target_date].tolist()
        if not target_idx_list:
            continue
        t_idx = target_idx_list[0]

        slice_7d = group.iloc[max(0, t_idx - 6) : t_idx + 1]
        slice_30d = group.iloc[max(0, t_idx - 29) : t_idx + 1]

        c_int_7d = float(slice_7d["weighted_conflict_intensity"].mean())
        c_int_30d = float(slice_30d["weighted_conflict_intensity"].mean())
        sent_7d = float(slice_7d["sentiment_score"].mean())
        sent_30d = float(slice_30d["sentiment_score"].mean())

        val_today = float(group.loc[t_idx, "weighted_conflict_intensity"])
        val_7d_ago_idx = max(0, t_idx - 7)
        val_7d_ago = float(group.loc[val_7d_ago_idx, "weighted_conflict_intensity"])
        int_7d_delta = val_today - val_7d_ago

        int_30d_std = float(slice_30d["weighted_conflict_intensity"].std(ddof=0))
        if np.isnan(int_30d_std):
            int_30d_std = 0.0

        evt_7d = float(slice_7d["event_count"].mean())
        evt_30d = float(slice_30d["event_count"].mean())
        vol_ratio = evt_7d / (evt_30d + 1e-5)

        mat_30d_sum = float(slice_30d["material_conflict_count"].sum())

        t_conc = trade_conc_map.get(c_str, 0.0500)
        c_exp = partner_exp_map.get(c_str, 65.0000)

        feats = {
            "conflict_intensity_7d_avg": round(c_int_7d, 4),
            "conflict_intensity_30d_avg": round(c_int_30d, 4),
            "sentiment_7d_avg": round(sent_7d, 4),
            "sentiment_30d_avg": round(sent_30d, 4),
            "intensity_7d_delta": round(int_7d_delta, 4),
            "intensity_30d_std": round(int_30d_std, 4),
            "volume_trend_7d_30d_ratio": round(vol_ratio, 4),
            "event_count_7d_avg": round(evt_7d, 2),
            "event_count_30d_avg": round(evt_30d, 2),
            "material_conflict_30d_sum": round(mat_30d_sum, 2),
            "trade_concentration": round(t_conc, 4),
            "conflict_partner_exposure": round(c_exp, 4),
        }

        feature_vectors.append(
            CountryFeatureVector(
                country_code=c_str,
                feature_date=target_date,
                features=feats,
            )
        )

    logger.info(
        "country_features_extracted",
        extra={"target_date": str(target_date), "countries_count": len(feature_vectors)},
    )
    return feature_vectors
