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

# Real bilateral trade partner mappings per commodity (ISO3, Origin Lat/Lon, Primary Chokepoint, Dest Lat/Lon, Port Name)
# Sourced from India Ministry of Commerce & Industry / DGFT, Port Authorities & UN Comtrade statistics
COMMODITY_PARTNERS_MAP = {
    # 1. Crude Oil -> Vadinar / Sikka (Gujarat) & Paradip (Odisha)
    "PETROLEUM_CRUDE": [
        ("IRQ", 33.31, 44.36, "HORMUZ", 22.4500, 69.8000, "Vadinar Port"),
        ("SAU", 24.71, 46.67, "HORMUZ", 22.4500, 69.8000, "Vadinar Port"),
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS", 20.2644, 86.6085, "Paradip Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 22.4500, 69.8000, "Vadinar Port"),
    ],
    # 2. Gold Bullion -> JNPT / Mumbai (Maharashtra)
    "GOLD": [
        ("CHE", 46.81, 8.22, "SUEZ", 18.9500, 72.9500, "Mumbai JNPT"),
        ("ARE", 24.45, 54.37, "HORMUZ", 18.9500, 72.9500, "Mumbai JNPT"),
        ("ZAF", -25.74, 28.18, "CAPE_GOOD_HOPE", 18.9500, 72.9500, "Mumbai JNPT"),
    ],
    # 3. Coal & Coke -> Paradip (Odisha) & Visakhapatnam (Andhra Pradesh)
    "COAL_COKE": [
        ("IDN", -6.20, 106.84, "MALACCA", 20.2644, 86.6085, "Paradip Port"),
        ("AUS", -25.27, 133.77, "MALACCA", 17.6868, 83.2986, "Visakhapatnam Port"),
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS", 20.2644, 86.6085, "Paradip Port"),
    ],
    # 4. Diamonds Unworked -> Surat / Hazira Port (Gujarat)
    "DIAMONDS_UNWORKED": [
        ("BEL", 50.85, 4.35, "ENGLISH_CHANNEL", 21.1086, 72.6358, "Hazira / Surat Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 21.1086, 72.6358, "Hazira / Surat Port"),
        ("ISR", 31.76, 35.21, "SUEZ", 21.1086, 72.6358, "Hazira / Surat Port"),
    ],
    # 5. Petroleum Products -> Mundra (Gujarat) & Chennai Port (Tamil Nadu)
    "PETROLEUM_PRODUCTS": [
        ("SAU", 24.71, 46.67, "HORMUZ", 22.7441, 69.7025, "Mundra Port"),
        ("QAT", 25.28, 51.53, "HORMUZ", 22.7441, 69.7025, "Mundra Port"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT", 13.0844, 80.2980, "Chennai Port"),
    ],
    # 6. Organic Chemicals -> Dahej Chemical PCPIR Port (Gujarat)
    "ORGANIC_CHEMICALS": [
        ("CHN", 39.90, 116.40, "MALACCA", 21.7000, 72.5800, "Dahej Port"),
        ("USA", 38.90, -77.03, "GIBRALTAR", 21.7000, 72.5800, "Dahej Port"),
        ("SAU", 24.71, 46.67, "HORMUZ", 21.7000, 72.5800, "Dahej Port"),
    ],
    # 7. Telecom Equipment -> Chennai Port / Sriperumbudur Corridor (Tamil Nadu)
    "TELECOM_EQUIPMENT": [
        ("CHN", 39.90, 116.40, "MALACCA", 13.0844, 80.2980, "Chennai Port"),
        ("VNM", 21.02, 105.83, "MALACCA", 13.0844, 80.2980, "Chennai Port"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT", 13.0844, 80.2980, "Chennai Port"),
    ],
    # 8. Vegetable Oils -> Kandla / Deendayal Port (Gujarat) & Haldia (West Bengal)
    "VEGETABLE_OILS": [
        ("IDN", -6.20, 106.84, "SUNDA", 22.8360, 70.2185, "Kandla Port"),
        ("MYS", 3.13, 101.68, "MALACCA", 22.0333, 88.0833, "Haldia Port"),
        ("ARG", -34.60, -58.38, "CAPE_GOOD_HOPE", 22.8360, 70.2185, "Kandla Port"),
    ],
    # 9. Plastics Raw -> Mundra Port & Dahej (Gujarat)
    "PLASTICS_RAW": [
        ("CHN", 39.90, 116.40, "MALACCA", 22.7441, 69.7025, "Mundra Port"),
        ("SAU", 24.71, 46.67, "HORMUZ", 21.7000, 72.5800, "Dahej Port"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT", 13.0844, 80.2980, "Chennai Port"),
    ],
    # 10. LNG Natural Gas -> Dahej LNG Terminal (Gujarat) & Kochi LNG (Kerala)
    "LNG_NATURAL_GAS": [
        ("QAT", 25.28, 51.53, "HORMUZ", 21.7000, 72.5800, "Dahej LNG Terminal"),
        ("ARE", 24.45, 54.37, "HORMUZ", 9.9656, 76.2711, "Kochi LNG Terminal"),
        ("USA", 38.90, -77.03, "GIBRALTAR", 21.7000, 72.5800, "Dahej LNG Terminal"),
    ],
    # 11. Integrated Circuits -> Chennai Port (Tamil Nadu)
    "INTEGRATED_CIRCUITS": [
        ("TWN", 25.03, 121.56, "TAIWAN_STRAIT", 13.0844, 80.2980, "Chennai Port"),
        ("CHN", 39.90, 116.40, "MALACCA", 13.0844, 80.2980, "Chennai Port"),
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT", 13.0844, 80.2980, "Chennai Port"),
    ],
    # 12. Fertilizers -> Paradip (Odisha) & Kandla (Gujarat)
    "FERTILIZERS": [
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS", 20.2644, 86.6085, "Paradip Port"),
        ("SAU", 24.71, 46.67, "HORMUZ", 22.8360, 70.2185, "Kandla Port"),
        ("CHN", 39.90, 116.40, "MALACCA", 20.2644, 86.6085, "Paradip Port"),
    ],
    # 13. Iron & Steel Imports -> Visakhapatnam Port (AP) & Paradip (Odisha)
    "IRON_STEEL": [
        ("KOR", 37.56, 126.97, "TAIWAN_STRAIT", 17.6868, 83.2986, "Visakhapatnam Port"),
        ("JPN", 35.67, 139.65, "TAIWAN_STRAIT", 17.6868, 83.2986, "Visakhapatnam Port"),
        ("CHN", 39.90, 116.40, "MALACCA", 20.2644, 86.6085, "Paradip Port"),
    ],
    # 14. Medical Instruments -> Mumbai JNPT (Maharashtra) & Chennai (Tamil Nadu)
    "MEDICAL_INSTRUMENTS": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 18.9500, 72.9500, "Mumbai JNPT"),
        ("DEU", 52.52, 13.40, "DANISH_STRAITS", 18.9500, 72.9500, "Mumbai JNPT"),
        ("CHN", 39.90, 116.40, "MALACCA", 13.0844, 80.2980, "Chennai Port"),
    ],
    # 15. Refined Copper -> Tuticorin VOC Port (Tamil Nadu) & Dahej (Gujarat)
    "COPPER_REFINED": [
        ("JPN", 35.67, 139.65, "TAIWAN_STRAIT", 8.7533, 78.1633, "Tuticorin Port"),
        ("MYS", 3.13, 101.68, "MALACCA", 8.7533, 78.1633, "Tuticorin Port"),
        ("CHL", -33.44, -70.66, "CAPE_GOOD_HOPE", 21.7000, 72.5800, "Dahej Port"),
    ],
    # Exports
    # 16. Refined Petroleum Products Export -> Jamnagar / Sikka Port (Gujarat)
    "REFINED_PETROLEUM_EXP": [
        ("NLD", 52.36, 4.90, "ENGLISH_CHANNEL", 22.4500, 69.8000, "Sikka / Jamnagar Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 22.4500, 69.8000, "Sikka / Jamnagar Port"),
        ("USA", 38.90, -77.03, "GIBRALTAR", 22.4500, 69.8000, "Sikka / Jamnagar Port"),
    ],
    # 17. Cut Diamonds & Jewelry Export -> Surat / Hazira Port (Gujarat) & Mumbai JNPT
    "CUT_DIAMONDS_JEWELRY": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 21.1086, 72.6358, "Hazira / Surat Port"),
        ("HKG", 22.31, 114.16, "TAIWAN_STRAIT", 21.1086, 72.6358, "Hazira / Surat Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 18.9500, 72.9500, "Mumbai JNPT"),
    ],
    # 18. Pharmaceuticals Export -> Visakhapatnam JLN Pharma SEZ & Mumbai JNPT
    "PHARMACEUTICALS": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 17.6868, 83.2986, "Visakhapatnam Port"),
        ("GBR", 51.50, -0.12, "ENGLISH_CHANNEL", 18.9500, 72.9500, "Mumbai JNPT"),
        ("ZAF", -25.74, 28.18, "CAPE_GOOD_HOPE", 17.6868, 83.2986, "Visakhapatnam Port"),
    ],
    # 19. Organic Chemicals Export -> Dahej Chemical PCPIR Port (Gujarat)
    "ORGANIC_CHEMICALS_EXP": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 21.7000, 72.5800, "Dahej Port"),
        ("CHN", 39.90, 116.40, "MALACCA", 21.7000, 72.5800, "Dahej Port"),
        ("SAU", 24.71, 46.67, "HORMUZ", 21.7000, 72.5800, "Dahej Port"),
    ],
    # 20. Telecom Instruments & Mobiles Export -> Chennai Port (Tamil Nadu)
    "TELECOM_INSTRUMENTS_EXP": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 13.0844, 80.2980, "Chennai Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 13.0844, 80.2980, "Chennai Port"),
        ("NLD", 52.36, 4.90, "ENGLISH_CHANNEL", 13.0844, 80.2980, "Chennai Port"),
    ],
    # 21. Motor Vehicles & Auto Export -> Chennai Port & Kamarajar Ennore (Tamil Nadu)
    "MOTOR_VEHICLES": [
        ("ZAF", -25.74, 28.18, "CAPE_GOOD_HOPE", 13.0844, 80.2980, "Chennai / Ennore Ro-Ro"),
        ("MEX", 19.43, -99.13, "PANAMA", 13.0844, 80.2980, "Chennai / Ennore Ro-Ro"),
        ("SAU", 24.71, 46.67, "HORMUZ", 18.9500, 72.9500, "Mumbai JNPT"),
    ],
    # 22. Machinery & Engineering Parts -> Mumbai JNPT (Maharashtra)
    "MACHINERY_PARTS": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 18.9500, 72.9500, "Mumbai JNPT"),
        ("DEU", 52.52, 13.40, "ENGLISH_CHANNEL", 18.9500, 72.9500, "Mumbai JNPT"),
        ("CHN", 39.90, 116.40, "MALACCA", 18.9500, 72.9500, "Mumbai JNPT"),
    ],
    # 23. Iron & Steel Export -> Paradip Port (Odisha) & Visakhapatnam (AP)
    "IRON_STEEL_EXP": [
        ("ITA", 41.90, 12.49, "GIBRALTAR", 20.2644, 86.6085, "Paradip Port"),
        ("BEL", 50.85, 4.35, "ENGLISH_CHANNEL", 20.2644, 86.6085, "Paradip Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 17.6868, 83.2986, "Visakhapatnam Port"),
    ],
    # 24. Cotton Yarn & Fabrics -> Tuticorin VOC Port (Tamil Nadu) & Mundra (Gujarat)
    "COTTON_YARN_FABRIC": [
        ("BGD", 23.81, 90.41, "MALACCA", 8.7533, 78.1633, "Tuticorin Port"),
        ("CHN", 39.90, 116.40, "MALACCA", 8.7533, 78.1633, "Tuticorin Port"),
        ("USA", 38.90, -77.03, "GIBRALTAR", 22.7441, 69.7025, "Mundra Port"),
    ],
    # 25. Rice Export -> Kandla Port (Basmati, Gujarat) & Kakinada Port (Non-Basmati, AP)
    "RICE": [
        ("SAU", 24.71, 46.67, "HORMUZ", 22.8360, 70.2185, "Kandla Port"),
        ("IRN", 35.68, 51.38, "HORMUZ", 22.8360, 70.2185, "Kandla Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 16.9890, 82.2874, "Kakinada Port"),
    ],
    # 26. Frozen Seafood & Shrimp -> Visakhapatnam Port (AP) & Kochi (Kerala)
    "CRUSTACEANS_SEAFOOD": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 17.6868, 83.2986, "Visakhapatnam Port"),
        ("CHN", 39.90, 116.40, "MALACCA", 9.9656, 76.2711, "Kochi Port"),
        ("JPN", 35.67, 139.65, "TAIWAN_STRAIT", 9.9656, 76.2711, "Kochi Port"),
    ],
    # 27. Refined Sugar -> Mormugao Port (Goa), Paradip (Odisha) & Kandla (Gujarat)
    "SUGAR_REFINED": [
        ("IDN", -6.20, 106.84, "MALACCA", 15.4167, 73.8000, "Mormugao Port"),
        ("BGD", 23.81, 90.41, "MALACCA", 20.2644, 86.6085, "Paradip Port"),
        ("SDN", 15.50, 32.55, "BAB_EL_MANDEB", 22.8360, 70.2185, "Kandla Port"),
    ],
    # 28. Leather Goods & Footwear -> Chennai Port (Tamil Nadu) & Kolkata Port (West Bengal)
    "LEATHER_GOODS": [
        ("DEU", 52.52, 13.40, "ENGLISH_CHANNEL", 13.0844, 80.2980, "Chennai Port"),
        ("USA", 38.90, -77.03, "GIBRALTAR", 13.0844, 80.2980, "Chennai Port"),
        ("ITA", 41.90, 12.49, "GIBRALTAR", 22.0333, 88.0833, "Kolkata Port"),
    ],
    # 29. Spices -> Kochi Port (Spice Coast, Kerala) & Tuticorin (Tamil Nadu)
    "SPICES": [
        ("USA", 38.90, -77.03, "GIBRALTAR", 9.9656, 76.2711, "Kochi Port"),
        ("CHN", 39.90, 116.40, "MALACCA", 9.9656, 76.2711, "Kochi Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 8.7533, 78.1633, "Tuticorin Port"),
    ],
    # 30. Tea & Coffee -> Kolkata Port (Darjeeling/Assam) & Kochi Port (Kerala/Karnataka)
    "TEA_COFFEE": [
        ("RUS", 55.75, 37.61, "TURKISH_STRAITS", 22.0333, 88.0833, "Kolkata Port"),
        ("ARE", 24.45, 54.37, "HORMUZ", 9.9656, 76.2711, "Kochi Port"),
        ("USA", 38.90, -77.03, "GIBRALTAR", 22.0333, 88.0833, "Kolkata Port"),
    ],
}


def update_india_trade_routes(db_url: str | None = None) -> dict[str, Any]:
    """Ingest and update India trade routes for all tracked commodities with authentic port destinations."""
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

                for p_data in partners:
                    partner = p_data[0]
                    orig_lat = p_data[1]
                    orig_long = p_data[2]
                    chk_code = p_data[3]
                    dest_lat = p_data[4] if len(p_data) > 4 else 18.950000
                    dest_long = p_data[5] if len(p_data) > 5 else 72.950000

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
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (commodity_code, partner_country) DO UPDATE
                        SET primary_chokepoint = EXCLUDED.primary_chokepoint,
                            origin_lat = EXCLUDED.origin_lat,
                            origin_long = EXCLUDED.origin_long,
                            dest_lat = EXCLUDED.dest_lat,
                            dest_long = EXCLUDED.dest_long,
                            risk_score = EXCLUDED.risk_score,
                            updated_at = NOW();
                        """,
                        (comm_code, partner, chk_code, orig_lat, orig_long, dest_lat, dest_long, risk_score),
                    )
                    routes_updated += 1

        conn.commit()

    logger.info(f"Updated {routes_updated} trade routes. Missing commodities: {missing_partners}")
    return {"routes_updated": routes_updated, "missing_commodities": missing_partners}
