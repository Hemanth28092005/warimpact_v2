"""Static strategic-infrastructure seed data.

Seeds approximate public-knowledge coordinates for military bases, nuclear
facilities, spaceports, undersea cable trunk routes, and pipeline corridors.
All rows are flagged is_estimated=true with a source citation, consistent
with the platform's data-honesty contract. Idempotent on (category, name).
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from ingestion.common.config import get_settings

logger = logging.getLogger(__name__)

CITATION = "Public-knowledge approximate coordinates; context layer only, not authoritative"

SITES: list[dict[str, Any]] = [
    {"category": "military_base", "name": "Diego Garcia (US/UK)", "cc": "IOT", "lat": -7.3195, "lon": 72.4228},
    {"category": "military_base", "name": "Naval Base Guam", "cc": "GUM", "lat": 13.4408, "lon": 144.6599},
    {"category": "military_base", "name": "Kadena Air Base", "cc": "JPN", "lat": 26.3511, "lon": 127.7689},
    {"category": "military_base", "name": "Yokosuka Naval Base", "cc": "JPN", "lat": 35.2886, "lon": 139.6703},
    {"category": "military_base", "name": "Ramstein Air Base", "cc": "DEU", "lat": 49.4369, "lon": 7.6003},
    {"category": "military_base", "name": "Incirlik Air Base", "cc": "TUR", "lat": 37.0011, "lon": 35.4258},
    {"category": "military_base", "name": "Al Udeid Air Base", "cc": "QAT", "lat": 25.1173, "lon": 51.3150},
    {"category": "military_base", "name": "Bahrain Naval Support Activity", "cc": "BHR", "lat": 26.2036, "lon": 50.6119},
    {"category": "military_base", "name": "Camp Lemonnier", "cc": "DJI", "lat": 11.5473, "lon": 43.1475},
    {"category": "military_base", "name": "Rota Naval Base", "cc": "ESP", "lat": 36.6408, "lon": -6.3500},
    {"category": "military_base", "name": "RAF Akrotiri", "cc": "GBR", "lat": 34.5908, "lon": 32.9889},
    {"category": "military_base", "name": "Thule / Pituffik Space Base", "cc": "GRL", "lat": 76.5313, "lon": -68.7031},
    {"category": "military_base", "name": "Hmeimim Air Base", "cc": "SYR", "lat": 35.4017, "lon": 35.9528},
    {"category": "military_base", "name": "Tartus Naval Facility", "cc": "SYR", "lat": 34.8959, "lon": 35.8850},
    {"category": "military_base", "name": "Severomorsk Naval Base", "cc": "RUS", "lat": 69.0731, "lon": 33.4181},
    {"category": "military_base", "name": "Kaliningrad Chernyakhovsk", "cc": "RUS", "lat": 54.6022, "lon": 20.5283},
    {"category": "military_base", "name": "Yulin Naval Base (Hainan)", "cc": "CHN", "lat": 18.2294, "lon": 109.6892},
    {"category": "military_base", "name": "Fiery Cross Reef", "cc": "CHN", "lat": 9.5492, "lon": 112.8889},
    {"category": "military_base", "name": "Hmas Stirling", "cc": "AUS", "lat": -32.2261, "lon": 115.6792},
    {"category": "military_base", "name": "Djibouti PLA Support Base", "cc": "DJI", "lat": 11.5750, "lon": 43.0950},
    {"category": "nuclear_site", "name": "Bushehr NPP", "cc": "IRN", "lat": 28.8296, "lon": 50.8877},
    {"category": "nuclear_site", "name": "Natanz Enrichment", "cc": "IRN", "lat": 33.7228, "lon": 51.7269},
    {"category": "nuclear_site", "name": "Fordow Enrichment", "cc": "IRN", "lat": 34.8846, "lon": 50.9959},
    {"category": "nuclear_site", "name": "Yongbyon Nuclear Complex", "cc": "PRK", "lat": 39.7989, "lon": 125.7542},
    {"category": "nuclear_site", "name": "Dimona / Negev Research Center", "cc": "ISR", "lat": 31.0036, "lon": 35.1469},
    {"category": "nuclear_site", "name": "Kahuta / KRL Enrichment", "cc": "PAK", "lat": 33.5936, "lon": 73.3819},
    {"category": "nuclear_site", "name": "Punggye-ri Test Site", "cc": "PRK", "lat": 41.2783, "lon": 129.0864},
    {"category": "nuclear_site", "name": "Novaya Zemlya Test Site", "cc": "RUS", "lat": 73.4100, "lon": 54.8800},
    {"category": "nuclear_site", "name": "Lop Nur Test Site", "cc": "CHN", "lat": 41.6500, "lon": 88.7000},
    {"category": "nuclear_site", "name": "Sellafield", "cc": "GBR", "lat": 54.4217, "lon": -3.5008},
    {"category": "nuclear_site", "name": "La Hague Reprocessing", "cc": "FRA", "lat": 49.6783, "lon": -1.8792},
    {"category": "nuclear_site", "name": "Zaporizhzhia NPP", "cc": "UKR", "lat": 47.5089, "lon": 34.5869},
    {"category": "nuclear_site", "name": "Fukushima Daiichi", "cc": "JPN", "lat": 37.4213, "lon": 141.0328},
    {"category": "nuclear_site", "name": "Rooppur NPP", "cc": "BGD", "lat": 24.0600, "lon": 89.0500},
    {"category": "spaceport", "name": "Cape Canaveral SFS", "cc": "USA", "lat": 28.4886, "lon": -80.5773},
    {"category": "spaceport", "name": "Vandenberg SFB", "cc": "USA", "lat": 34.7420, "lon": -120.5724},
    {"category": "spaceport", "name": "Baikonur Cosmodrome", "cc": "KAZ", "lat": 45.9650, "lon": 63.3050},
    {"category": "spaceport", "name": "Plesetsk Cosmodrome", "cc": "RUS", "lat": 62.9256, "lon": 40.5789},
    {"category": "spaceport", "name": "Kourou (Guiana Space Centre)", "cc": "FRA", "lat": 5.2389, "lon": -52.7683},
    {"category": "spaceport", "name": "Satish Dhawan SDSC", "cc": "IND", "lat": 13.7199, "lon": 80.2304},
    {"category": "spaceport", "name": "Wenchang LC", "cc": "CHN", "lat": 19.6144, "lon": 110.9511},
    {"category": "spaceport", "name": "Tanegashima SC", "cc": "JPN", "lat": 30.3992, "lon": 130.9686},
    {"category": "spaceport", "name": "Naro Space Center", "cc": "KOR", "lat": 34.4319, "lon": 127.5350},
    {"category": "spaceport", "name": "Sohae Launch Station", "cc": "PRK", "lat": 40.8539, "lon": 124.7050},
]

CABLE_ROUTES: list[dict[str, Any]] = [
    {"name": "SEA-ME-WE 5 (approx trunk)", "fn": "Singapore", "flat": 1.2903, "flon": 103.8520, "tn": "Marseille", "tlat": 43.2965, "tlon": 5.3698},
    {"name": "SEA-ME-WE 5 (Red Sea segment)", "fn": "Jeddah", "flat": 21.4858, "flon": 39.1925, "tn": "Marseille", "tlat": 43.2965, "tlon": 5.3698},
    {"name": "AAE-1 (approx trunk)", "fn": "Hong Kong", "flat": 22.3193, "flon": 114.1694, "tn": "Marseille", "tlat": 43.2965, "tlon": 5.3698},
    {"name": "MAREA (approx)", "fn": "Virginia Beach", "flat": 36.8508, "flon": -75.9779, "tn": "Bilbao", "tlat": 43.2630, "tlon": -2.9350},
    {"name": "Grace Hopper (approx)", "fn": "New York", "flat": 40.7128, "flon": -74.0060, "tn": "Bude", "tlat": 50.8287, "tlon": -4.5497},
    {"name": "JUPITER (approx)", "fn": "Los Angeles", "flat": 33.7701, "flon": -118.1937, "tn": "Maruyama", "tlat": 34.8500, "tlon": 139.9500},
    {"name": "2Africa (Hormuz segment)", "fn": "Dubai", "flat": 25.2048, "flon": 55.2708, "tn": "Zafarana", "tlat": 28.7300, "tlon": 32.7200},
    {"name": "INDIA-Asia (approx)", "fn": "Mumbai", "flat": 19.0760, "flon": 72.8777, "tn": "Singapore", "tlat": 1.2903, "tlon": 103.8520},
    {"name": "PEACE Cable (approx trunk)", "fn": "Karachi", "flat": 24.8607, "flon": 67.0011, "tn": "Marseille", "tlat": 43.2965, "tlon": 5.3698},
    {"name": "EIG (approx trunk)", "fn": "Chennai", "flat": 13.0827, "flon": 80.2707, "tn": "Marseille", "tlat": 43.2965, "tlon": 5.3698},
    {"name": "PIPELINE: Druzhba (approx)", "fn": "Samara", "flat": 53.1959, "flon": 50.1002, "tn": "Schwedt", "tlat": 53.0576, "tlon": 14.3000},
    {"name": "PIPELINE: East-West Crude (approx)", "fn": "Abqaiq", "flat": 25.9333, "flon": 49.6667, "tn": "Yanbu", "tlat": 24.0895, "tlon": 38.0618},
    {"name": "PIPELINE: TAPI (approx)", "fn": "Turkmenbashi", "flat": 37.3400, "flon": 62.0500, "tn": "Fazilka", "tlat": 30.4000, "tlon": 74.0300},
]

CATEGORY_TO_KEY = {
    "military_base": "sites",
    "nuclear_site": "sites",
    "spaceport": "sites",
    "undersea_cable": "cables",
    "pipeline": "cables",
}


def seed_intel(conn: psycopg.Connection) -> dict[str, int]:
    seeded_sites = 0
    seeded_routes = 0
    with conn.cursor() as cur:
        for s in SITES:
            cur.execute(
                """
                INSERT INTO intel_sites (category, name, country_code, latitude, longitude, source_citation, is_estimated)
                VALUES (%s, %s, %s, %s, %s, %s, true)
                ON CONFLICT (category, name) DO NOTHING
                """,
                (s["category"], s["name"], s["cc"], s["lat"], s["lon"], CITATION),
            )
            seeded_sites += cur.rowcount
        for c in CABLE_ROUTES:
            cat = "undersea_cable" if c["name"].startswith(("SEA", "AAE", "MAREA", "Grace", "JUPITER", "2Africa", "INDIA", "PEACE", "EIG")) else "pipeline"
            cur.execute(
                """
                INSERT INTO intel_routes (category, name, from_name, from_lat, from_long, to_name, to_lat, to_long, source_citation, is_estimated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                ON CONFLICT (category, name) DO NOTHING
                """,
                (cat, c["name"], c["fn"], c["flat"], c["flon"], c["tn"], c["tlat"], c["tlon"], CITATION),
            )
            seeded_routes += cur.rowcount
    return {"sites_seeded": seeded_sites, "routes_seeded": seeded_routes}


def run_intel_seed_sync() -> dict[str, int]:
    settings = get_settings()
    with psycopg.connect(settings.psycopg_database_url) as conn:
        with conn.transaction():
            counts = seed_intel(conn)
    logger.info("intel_seed_complete", extra=counts)
    return counts
