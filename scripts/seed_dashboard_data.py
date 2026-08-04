"""Seed script for Phase 6a Dashboard Data Layer.

Seeds:
1. tracked_commodities (30 top India import/export commodities)
2. chokepoints (13 global maritime chokepoints with EIA 2023 baseline MBD)
3. world_boundaries (GeoJSON boundaries for 38 in-scope countries)
"""

import json
import logging
import urllib.request
import psycopg
from psycopg.types.json import Jsonb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_URL = "user=war_impact password=war_impact_password dbname=war_impact host=localhost port=5432"

COMMODITIES_DATA = [
    # Top 15 Imports by Value
    ("PETROLEUM_CRUDE", "Petroleum Crude", "Energy", "import", 132400000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 2709)"),
    ("GOLD", "Gold (Unwrought / Semi-Manufactured)", "Precious Metals", "import", 45500000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 7108)"),
    ("COAL_COKE", "Coal, Briquettes & Solid Fuels", "Energy", "import", 38200000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 2701)"),
    ("DIAMONDS_UNWORKED", "Diamonds Unworked / Unsorted", "Precious Metals", "import", 23000000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 7102)"),
    ("PETROLEUM_PRODUCTS", "Petroleum Products & Oils", "Energy", "import", 22100000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 2710)"),
    ("ORGANIC_CHEMICALS", "Organic Chemicals", "Chemicals", "import", 18400000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 2902)"),
    ("TELECOM_EQUIPMENT", "Telecom Equipment & Mobiles", "Electronics", "import", 15700000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 8517)"),
    ("VEGETABLE_OILS", "Vegetable Oils & Palm Oil", "Agriculture", "import", 14800000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 1511)"),
    ("PLASTICS_RAW", "Plastics in Primary Forms", "Materials", "import", 14200000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 3901)"),
    ("LNG_NATURAL_GAS", "Liquefied Natural Gas (LNG)", "Energy", "import", 13500000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 2711)"),
    ("INTEGRATED_CIRCUITS", "Electronic Integrated Circuits", "Electronics", "import", 12300000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 8542)"),
    ("FERTILIZERS", "Mineral & Chemical Fertilizers", "Agriculture", "import", 11600000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 3105)"),
    ("IRON_STEEL", "Iron & Steel Flat Products", "Metals", "import", 10500000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 7208)"),
    ("MEDICAL_INSTRUMENTS", "Medical Instruments & Appliances", "Healthcare", "import", 6200000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 9018)"),
    ("COPPER_REFINED", "Refined Copper & Alloys", "Metals", "import", 5800000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 7403)"),
    # Top 15 Exports by Value
    ("REFINED_PETROLEUM_EXP", "Refined Petroleum & Motor Spirits", "Energy", "export", 62200000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 2710)"),
    ("CUT_DIAMONDS_JEWELRY", "Cut Diamonds & Jewelry", "Precious Metals", "export", 32800000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 7113)"),
    ("PHARMACEUTICALS", "Pharmaceutical Products & Medicaments", "Healthcare", "export", 27900000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 3004)"),
    ("ORGANIC_CHEMICALS_EXP", "Organic Chemicals Export", "Chemicals", "export", 17500000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 2905)"),
    ("TELECOM_INSTRUMENTS_EXP", "Telecom Instruments & Smartphones", "Electronics", "export", 15600000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 8517)"),
    ("MOTOR_VEHICLES", "Motor Vehicles & Automobiles", "Manufacturing", "export", 14100000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 8703)"),
    ("MACHINERY_PARTS", "Machinery & Mechanical Appliances", "Manufacturing", "export", 13600000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 8483)"),
    ("IRON_STEEL_EXP", "Iron & Steel Products Export", "Metals", "export", 12700000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 7202)"),
    ("COTTON_YARN_FABRIC", "Cotton Yarn, Fabrics & Made-ups", "Textiles", "export", 11200000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 5205)"),
    ("RICE", "Rice (Basmati & Non-Basmati)", "Agriculture", "export", 10400000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 1006)"),
    ("CRUSTACEANS_SEAFOOD", "Frozen Shrimp & Crustaceans", "Agriculture", "export", 7400000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 0306)"),
    ("SUGAR_REFINED", "Cane Sugar & Refined Sugar", "Agriculture", "export", 5700000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 1701)"),
    ("LEATHER_GOODS", "Leather Goods & Footwear", "Textiles", "export", 4800000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 4202)"),
    ("SPICES", "Spices (Pepper, Cardamom, Turmeric)", "Agriculture", "export", 4200000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 0910)"),
    ("TEA_COFFEE", "Tea & Coffee Extracts", "Agriculture", "export", 2100000000.00, "India Ministry of Commerce & Industry / DGFT 2023-24 Statistics (HS 0901)"),
]

CHOKEPOINTS_DATA = [
    ("HORMUZ", "Strait of Hormuz", 26.540000, 56.420000, 21.00, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("MALACCA", "Strait of Malacca", 1.430000, 103.010000, 16.00, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("BAB_EL_MANDEB", "Bab el-Mandeb Strait", 12.590000, 43.340000, 6.20, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("SUEZ", "Suez Canal & SUMED Pipeline", 29.930000, 32.560000, 5.50, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("TURKISH_STRAITS", "Bosporus & Dardanelles", 40.720000, 28.980000, 3.20, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("DANISH_STRAITS", "Danish Straits", 55.670000, 12.570000, 3.20, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("PANAMA", "Panama Canal", 9.080000, -79.680000, 1.10, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("CAPE_GOOD_HOPE", "Cape of Good Hope", -34.350000, 18.470000, 5.80, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("GIBRALTAR", "Strait of Gibraltar", 35.960000, -5.600000, 4.50, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("TAIWAN_STRAIT", "Taiwan Strait", 24.000000, 119.500000, 4.00, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("LOMBOK", "Lombok Strait", -8.460000, 115.720000, 1.50, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("SUNDA", "Sunda Strait", -5.920000, 105.780000, 1.00, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
    ("ENGLISH_CHANNEL", "English Channel", 50.500000, 0.500000, 2.50, 2023, "US EIA World Oil Transit Chokepoints Report 2023"),
]

IN_SCOPE_ISO3 = [
    "USA", "CHN", "IND", "RUS", "UKR", "ISR", "IRN", "SAU", "TUR", "DEU",
    "FRA", "GBR", "JPN", "KOR", "TWN", "PAK", "AFG", "SYR", "IRQ", "YEM",
    "EGY", "SDN", "ETH", "SOM", "NGA", "ZAF", "BRA", "MEX", "COL", "VEN",
    "MMR", "IDN", "MYS", "PHL", "VNM", "POL", "BLR", "PRK"
]

GEOJSON_URL = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"


def seed_commodities(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        for code, name, cat, trade_type, val, citation in COMMODITIES_DATA:
            cur.execute(
                """
                INSERT INTO tracked_commodities (commodity_code, name, category, trade_type, annual_value_usd, source_citation)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (commodity_code) DO UPDATE
                SET name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    trade_type = EXCLUDED.trade_type,
                    annual_value_usd = EXCLUDED.annual_value_usd,
                    source_citation = EXCLUDED.source_citation;
                """,
                (code, name, cat, trade_type, val, citation),
            )
        cur.execute("SELECT COUNT(*) FROM tracked_commodities;")
        count = cur.fetchone()[0]
        logger.info(f"Seeded tracked_commodities: {count} rows")
        return count


def seed_chokepoints(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        for code, name, lat, long_, mbd, year, citation in CHOKEPOINTS_DATA:
            cur.execute(
                """
                INSERT INTO chokepoints (code, name, lat, long, baseline_mbd, source_year, last_disruption_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                SET name = EXCLUDED.name,
                    lat = EXCLUDED.lat,
                    long = EXCLUDED.long,
                    baseline_mbd = EXCLUDED.baseline_mbd,
                    source_year = EXCLUDED.source_year;
                """,
                (code, name, lat, long_, mbd, year, f"Baseline report: {citation}"),
            )
        cur.execute("SELECT COUNT(*) FROM chokepoints;")
        count = cur.fetchone()[0]
        logger.info(f"Seeded chokepoints: {count} rows")
        return count


def seed_world_boundaries(conn: psycopg.Connection) -> int:
    logger.info("Fetching country boundaries GeoJSON for full-globe (~200 country) coverage...")
    req = urllib.request.Request(GEOJSON_URL, headers={"User-Agent": "WarImpactPlatform/1.0"})
    with urllib.request.urlopen(req) as resp:
        geojson_data = json.loads(resp.read().decode("utf-8"))

    seeded_count = 0
    with conn.cursor() as cur:
        for feature in geojson_data.get("features", []):
            props = feature.get("properties", {})
            iso3 = props.get("ISO3166-1-Alpha-3") or props.get("ISO_A3") or props.get("iso_a3") or props.get("ADM0_A3")
            name = props.get("name") or props.get("ADMIN") or props.get("NAME")
            if iso3 == "-99" or not iso3:
                if name == "France":
                    iso3 = "FRA"
                elif name:
                    iso3 = name[:3].upper()

            if iso3 and name:
                iso3_clean = iso3.upper()
                cur.execute(
                    """
                    INSERT INTO world_boundaries (iso_a3, name, geojson)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (iso_a3) DO UPDATE
                    SET name = EXCLUDED.name,
                        geojson = EXCLUDED.geojson;
                    """,
                    (iso3_clean, name, Jsonb(feature)),
                )
                seeded_count += 1

        cur.execute("SELECT COUNT(*) FROM world_boundaries;")
        total = cur.fetchone()[0]
        logger.info(f"Seeded world_boundaries: {total} total global countries")
        return total


def main() -> None:
    logger.info("Starting Phase 6a database seeding...")
    with psycopg.connect(DB_URL) as conn:
        c_count = seed_commodities(conn)
        chk_count = seed_chokepoints(conn)
        bnd_count = seed_world_boundaries(conn)
        conn.commit()

    print("\n" + "=" * 60)
    print("PHASE 6A SEEDING COMPLETE")
    print(f"  - tracked_commodities: {c_count} rows")
    print(f"  - chokepoints: {chk_count} rows")
    print(f"  - world_boundaries: {bnd_count} rows")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
