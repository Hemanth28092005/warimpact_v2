"""India Trade Routes & Combined Risk Scoring Engine.

Maps top trade partners for India's 30 tracked commodities.
Computes route risk score combining:
- CII_partner (40%)
- Aggression_partner_IN (35%)
- Disruption_chokepoint (25%)

Upserts into india_trade_routes on (commodity_code, partner_country).
"""

import logging
from typing import Any
import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

# Real bilateral trade partner mappings per commodity (ISO3, Origin Lat/Lon, Primary Chokepoint)
# Sourced from India Ministry of Commerce & Industry / DGFT & UN Comtrade statistics 2023-2024
COMMODITY_PARTNERS_MAP = {
    "PETROLEUM_CRUDE": [
        ("IRQ", 33.31, 44.36, "HORMUZ"),
        ("SAU", 24.71, 46.67, "HORMUZ"),
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
    ],
    "GOLD": [
        ("CHE", 46.81, 8.22, "SUEZ"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
        ("ZAF", -25.74, 28.18, "CAPE_GOOD_HOPE"),
    ],
    "COAL_COKE": [
        ("IDN", -6.20, 106.84, "MALACCA"),
        ("AUS", -25.27, 133.77, "MALACCA"),
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS"),
    ],
    "DIAMONDS_UNWORKED": [
        ("BEL", 50.85, 4.35, "ENGLISH_CHANNEL"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
        ("ISR", 31.76, 35.21, "SUEZ"),
    ],
    "PETROLEUM_PRODUCTS": [
        ("SAU", 24.71, 46.67, "HORMUZ"),
        ("QAT", 25.28, 51.53, "HORMUZ"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT"),
    ],
    "ORGANIC_CHEMICALS": [
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("SAU", 24.71, 46.67, "HORMUZ"),
    ],
    "TELECOM_EQUIPMENT": [
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("VNM", 21.02, 105.83, "MALACCA"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT"),
    ],
    "VEGETABLE_OILS": [
        ("IDN", -6.20, 106.84, "SUNDA"),
        ("MYS", 3.13, 101.68, "MALACCA"),
        ("ARG", -34.60, -58.38, "CAPE_GOOD_HOPE"),
    ],
    "PLASTICS_RAW": [
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("SAU", 24.71, 46.67, "HORMUZ"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT"),
    ],
    "LNG_NATURAL_GAS": [
        ("QAT", 25.28, 51.53, "HORMUZ"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
        ("USA", 38.90, -77.03, "GIBRALTAR"),
    ],
    "INTEGRATED_CIRCUITS": [
        ("TWN", 25.03, 121.56, "TAIWAN_STRAIT"),
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT"),
    ],
    "FERTILIZERS": [
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS"),
        ("SAU", 24.71, 46.67, "HORMUZ"),
        ("CHN", 39.90, 116.40, "MALACCA"),
    ],
    "IRON_STEEL": [
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT"),
        ("JPN", 35.67, 139.65, "TAIWAN_STRAIT"),
        ("CHN", 39.90, 116.40, "MALACCA"),
    ],
    "MEDICAL_INSTRUMENTS": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("DEU", 52.52, 13.40, "DANISH_STRAITS"),
        ("CHN", 39.90, 116.40, "MALACCA"),
    ],
    "COPPER_REFINED": [
        ("JPN", 35.67, 139.65, "TAIWAN_STRAIT"),
        ("MYS", 3.13, 101.68, "MALACCA"),
        ("CHL", -33.44, -70.66, "CAPE_GOOD_HOPE"),
    ],
    # Exports
    "REFINED_PETROLEUM_EXP": [
        ("NLD", 52.36, 4.90, "ENGLISH_CHANNEL"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
        ("USA", 38.90, -77.03, "GIBRALTAR"),
    ],
    "CUT_DIAMONDS_JEWELRY": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("HKG", 22.31, 114.16, "TAIWAN_STRAIT"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
    ],
    "PHARMACEUTICALS": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("GBR", 51.50, -0.12, "ENGLISH_CHANNEL"),
        ("ZAF", -25.74, 28.18, "CAPE_GOOD_HOPE"),
    ],
    "ORGANIC_CHEMICALS_EXP": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("SAU", 24.71, 46.67, "HORMUZ"),
    ],
    "TELECOM_INSTRUMENTS_EXP": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
        ("NLD", 52.36, 4.90, "ENGLISH_CHANNEL"),
    ],
    "MOTOR_VEHICLES": [
        ("ZAF", -25.74, 28.18, "CAPE_GOOD_HOPE"),
        ("MEX", 19.43, -99.13, "PANAMA"),
        ("SAU", 24.71, 46.67, "HORMUZ"),
    ],
    "MACHINERY_PARTS": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("DEU", 52.52, 13.40, "ENGLISH_CHANNEL"),
        ("CHN", 39.90, 116.40, "MALACCA"),
    ],
    "IRON_STEEL_EXP": [
        ("ITA", 41.90, 12.49, "GIBRALTAR"),
        ("BEL", 50.85, 4.35, "ENGLISH_CHANNEL"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
    ],
    "COTTON_YARN_FABRIC": [
        ("BGD", 23.81, 90.41, "MALACCA"),
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("USA", 38.90, -77.03, "GIBRALTAR"),
    ],
    "RICE": [
        ("SAU", 24.71, 46.67, "HORMUZ"),
        ("IRN", 35.68, 51.38, "HORMUZ"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
    ],
    "CRUSTACEANS_SEAFOOD": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("JPN", 35.67, 139.65, "TAIWAN_STRAIT"),
    ],
    "SUGAR_REFINED": [
        ("IDN", -6.20, 106.84, "MALACCA"),
        ("BGD", 23.81, 90.41, "MALACCA"),
        ("SDN", 15.50, 32.55, "BAB_EL_MANDEB"),
    ],
    "LEATHER_GOODS": [
        ("DEU", 52.52, 13.40, "ENGLISH_CHANNEL"),
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("ITA", 41.90, 12.49, "GIBRALTAR"),
    ],
    "SPICES": [
        ("USA", 38.90, -77.03, "GIBRALTAR"),
        ("CHN", 39.90, 116.40, "MALACCA"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
    ],
    "TEA_COFFEE": [
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS"),
        ("ARE", 24.45, 54.37, "HORMUZ"),
        ("USA", 38.90, -77.03, "GIBRALTAR"),
    ],
}


def update_india_trade_routes(db_url: str | None = None) -> dict[str, Any]:
    """Ingest and update India trade routes for all tracked commodities."""
    if not db_url:
        db_url = get_settings().psycopg_database_url

    logger.info("Starting India trade routes calculation pipeline...")
    routes_updated = 0
    missing_partners = []

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Fetch latest CII scores
            cur.execute("SELECT country_code, cii_score FROM country_instability_index ORDER BY score_date DESC;")
            cii_map = {row[0]: float(row[1]) for row in cur.fetchall()}

            # Fetch latest aggression scores against IND
            cur.execute(
                """
                SELECT country_a, aggression_score FROM country_aggression_scores
                WHERE country_b = 'IND';
                """
            )
            aggr_map = {row[0]: float(row[1] or 0.0) for row in cur.fetchall()}

            # Fetch latest chokepoint disruption scores
            cur.execute("SELECT code, disruption_score FROM chokepoints;")
            chokepoint_map = {row[0]: float(row[1]) for row in cur.fetchall()}

            cur.execute("SELECT commodity_code FROM tracked_commodities;")
            all_commodities = [r[0] for r in cur.fetchall()]

            for comm_code in all_commodities:
                partners = COMMODITY_PARTNERS_MAP.get(comm_code)
                if not partners:
                    missing_partners.append(comm_code)
                    logger.warning(f"No trade partner mapping found for commodity {comm_code}")
                    continue

                for partner, orig_lat, orig_long, chk_code in partners:
                    cii_val = cii_map.get(partner, 35.0)
                    aggr_val = aggr_map.get(partner, 10.0)

                    if chk_code:
                        chk_val = chokepoint_map.get(chk_code, 0.0)
                        # Standard Formula: 0.40 * CII + 0.35 * Aggression + 0.25 * Disruption
                        risk_score = round(0.40 * cii_val + 0.35 * aggr_val + 0.25 * chk_val, 2)
                    else:
                        # Weight Redistribution Formula when primary_chokepoint IS NULL:
                        # Redistribute 0.25 disruption weight across CII and Aggression (0.40/0.75 & 0.35/0.75)
                        risk_score = round((0.40 / 0.75) * cii_val + (0.35 / 0.75) * aggr_val, 2)

                    cur.execute(
                        """
                        INSERT INTO india_trade_routes (
                            commodity_code, partner_country, primary_chokepoint,
                            origin_lat, origin_long, dest_lat, dest_long, risk_score, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, 18.950000, 72.950000, %s, NOW())
                        ON CONFLICT (commodity_code, partner_country) DO UPDATE
                        SET primary_chokepoint = EXCLUDED.primary_chokepoint,
                            origin_lat = EXCLUDED.origin_lat,
                            origin_long = EXCLUDED.origin_long,
                            risk_score = EXCLUDED.risk_score,
                            updated_at = NOW();
                        """,
                        (comm_code, partner, chk_code, orig_lat, orig_long, risk_score),
                    )
                    routes_updated += 1

        conn.commit()

    logger.info(f"Updated {routes_updated} trade routes. Missing commodities: {missing_partners}")
    return {"routes_updated": routes_updated, "missing_commodities": missing_partners}
