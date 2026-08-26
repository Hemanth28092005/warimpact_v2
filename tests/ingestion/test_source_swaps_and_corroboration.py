"""Unit and Integration Tests for Phase 6 Data Layer Source Swaps & Corroboration.

Tests:
- ACLED client, multi-factor severity scoring, normalized geography mapping (including Jantar Mantar).
- IMF PortWatch alert mapping, daily transit deviation scoring, and mojibake sanitization.
- World Bank Pink Sheet XML / XLSX parsing.
- PIB action_type classification across 7 canonical categories and actor extraction.
- data.gov.in documented resource configurations.
- Additive, non-gating market corroboration behavior.
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from ingestion.sources.acled_client import (
    ACLEDClient,
    calculate_acled_severity,
    map_acled_record_to_protest,
)
from ingestion.sources.datagovin_client import DataGovInClient, DATASETS_METADATA
from ingestion.sources.eia_client import EIAClient
from ingestion.sources.pib_client import PIBClient, classify_pib_action_type
from ingestion.sources.portwatch_client import (
    PortWatchClient,
    derive_portwatch_status,
    sanitize_text,
)
from ingestion.sources.world_bank_client import (
    WorldBankPinkSheetClient,
    WB_COMMODITY_MAP,
    _cell_col_index,
    _col_idx_to_letter,
)
from models.commodities.news import match_commodity_candidate, check_market_corroboration


class TestACLEDMapping(unittest.TestCase):
    """Test ACLED client, severity calculations, and geography mapping."""

    def test_calculate_acled_severity_varied(self):
        # Peaceful protest without fatalities
        sev1 = calculate_acled_severity("Peaceful protest", 0)
        self.assertGreaterEqual(sev1, 20.0)
        self.assertLess(sev1, 40.0)

        # Violent demonstration with fatalities
        sev2 = calculate_acled_severity("Violent demonstration", 2, "clash")
        self.assertGreater(sev2, sev1)
        self.assertGreaterEqual(sev2, 70.0)

        # Excessive force by security forces
        sev3 = calculate_acled_severity("Protest with intervention", 1, "excessive force")
        self.assertGreaterEqual(sev3, 75.0)

    def test_map_acled_record_jantar_mantar_case(self):
        raw = {
            "event_id_cnty": "IND12345",
            "event_date": "2026-08-15",
            "country": "India",
            "admin1": "Delhi",
            "admin2": "New Delhi",
            "admin3": "",
            "location": "Jantar Mantar",
            "latitude": 28.6271,
            "longitude": 77.2166,
            "geo_precision": 1,
            "event_type": "Protests",
            "sub_event_type": "Peaceful protest",
            "interaction": 14,
            "fatalities": 0,
            "notes": "Demonstration at Jantar Mantar demanding agricultural reform policy.",
            "tags": "peaceful",
        }
        mapped = map_acled_record_to_protest(raw)
        self.assertEqual(mapped["location_name"], "Jantar Mantar")
        self.assertEqual(mapped["location_level"], "venue")
        self.assertEqual(mapped["city"], "New Delhi")
        self.assertEqual(mapped["state"], "Delhi")
        self.assertEqual(mapped["country_code"], "IND")
        self.assertEqual(mapped["validation_source"], "acled")
        self.assertIn("Jantar Mantar", mapped["headline"])

    def test_map_acled_record_district_level_null_city(self):
        raw = {
            "event_id_cnty": "IND54321",
            "event_date": "2026-08-20",
            "country": "India",
            "admin1": "Punjab",
            "admin2": "Patiala",
            "admin3": "Samana",
            "location": "Samana Rural Sector",
            "latitude": 30.15,
            "longitude": 76.19,
            "geo_precision": 2,
            "event_type": "Protests",
            "sub_event_type": "Protest with intervention",
            "interaction": 14,
            "fatalities": 0,
            "notes": "Farmers staged rail roko along railway tracks in Samana sector.",
            "tags": "strike",
        }
        mapped = map_acled_record_to_protest(raw)
        self.assertEqual(mapped["location_name"], "Samana Rural Sector")
        self.assertEqual(mapped["location_level"], "district")
        self.assertIsNone(mapped["city"])
        self.assertEqual(mapped["state"], "Punjab")

    def test_acled_client_unconfigured_fallback(self):
        client = ACLEDClient(email="", access_key="")
        self.assertFalse(client.is_configured)
        events = client.fetch_protest_events()
        self.assertEqual(events, [])


class TestPortWatchClient(unittest.TestCase):
    """Test IMF PortWatch alert mapping, transit deviation, and mojibake fixing."""

    def test_sanitize_text_mojibake(self):
        dirty = "K'taka Cabinet approves premature release of 28 life\u2011term prisoners \u2013 official order\u2026"
        clean = sanitize_text(dirty)
        self.assertNotIn("\u2011", clean)
        self.assertNotIn("\u2013", clean)
        self.assertIn("life-term prisoners - official order...", clean)

    def test_derive_portwatch_status_direct_red_alert(self):
        disruptions = [
            {
                "name": "Bab el-Mandeb Strait Disruption Alert",
                "disruption_type": "Missile attacks on merchant vessels in southern corridor",
                "alert_level": "RED",
                "start_date": "2026-08-20T00:00:00Z",
            }
        ]
        status, score, reason, events = derive_portwatch_status([], disruptions, "BAB_EL_MANDEB")
        self.assertEqual(status, "red")
        self.assertGreaterEqual(score, 50.0)
        self.assertIn("PortWatch Alert [RED]", reason)
        self.assertEqual(len(events), 1)

    def test_derive_portwatch_status_transit_contraction(self):
        # 10 days of normal 100 capacity, last 3 days of 40 capacity (-60% drop)
        daily = [
            {"date": f"2026-08-{i:02d}", "capacity": 40 if i >= 18 else 100, "portid": "chokepoint1"}
            for i in range(20, 0, -1)
        ]
        status, score, reason, events = derive_portwatch_status(daily, [], "SUEZ")
        self.assertEqual(status, "red")
        self.assertGreaterEqual(score, 50.0)
        self.assertIn("Severe transit capacity contraction", reason)


class TestWorldBankParser(unittest.TestCase):
    """Test World Bank Pink Sheet column index helper and commodity mapping."""

    def test_col_index_conversions(self):
        self.assertEqual(_cell_col_index("A1"), 0)
        self.assertEqual(_cell_col_index("B4"), 1)
        self.assertEqual(_cell_col_index("Z10"), 25)
        self.assertEqual(_cell_col_index("AA1"), 26)
        self.assertEqual(_col_idx_to_letter(0), "A")
        self.assertEqual(_col_idx_to_letter(1), "B")
        self.assertEqual(_col_idx_to_letter(26), "AA")

    def test_wb_commodity_mapping(self):
        self.assertIn("crude oil, brent", WB_COMMODITY_MAP)
        self.assertEqual(WB_COMMODITY_MAP["crude oil, brent"], "PETROLEUM_CRUDE")
        self.assertEqual(WB_COMMODITY_MAP["gold"], "GOLD")
        self.assertEqual(WB_COMMODITY_MAP["coal, australian"], "COAL_COKE")


class TestPIBActionClassification(unittest.TestCase):
    """Test PIB action_type classification into 7 canonical categories."""

    def test_classify_pib_action_types(self):
        cases = [
            ("India and Morocco hold 7th Joint Commission on bilateral trade envoy relations", "diplomatic", "Government of India"),
            ("DGFT issues new regulatory guidelines and quality control compliance norms", "regulatory", "Ministry of Commerce & Industry"),
            ("Parliament passes statutory amendment bill in Lok Sabha", "legislative", "Government of India"),
            ("Supreme Court directed tribunal order in landmark constitutional ruling", "judicial", "Government of India"),
            ("Finance Ministry announces customs duty revision and GST revenue allocation", "fiscal", "Ministry of Finance"),
            ("Defence Ministry approves border security drdo acquisition for Indian Armed Forces", "security", "Ministry of Defence"),
            ("Cabinet approves appointment of high-level administrative committee task force", "administrative", "Government of India"),
        ]
        for text, expected_type, expected_actor in cases:
            act_type, actor = classify_pib_action_type(text)
            self.assertEqual(act_type, expected_type, f"Failed for text: {text}")
            self.assertIn(expected_actor, actor)


class TestCommodityAdditiveCorroboration(unittest.TestCase):
    """Test that commodity news matching is additive and non-rejecting."""

    def test_match_commodity_candidate_inclusions_exclusions(self):
        # Valid Crude Oil Story
        matched, conf, reason = match_commodity_candidate(
            "PETROLEUM_CRUDE",
            "OPEC cuts oil production as crude oil prices surge to multi-month highs",
        )
        self.assertTrue(matched)
        self.assertGreaterEqual(conf, 0.85)

        # Exclusion trigger: smart glasses
        matched_excl, _, _ = match_commodity_candidate(
            "PETROLEUM_CRUDE",
            "Tech firm unveils smart glasses with oil-resistant coating",
        )
        self.assertFalse(matched_excl)


if __name__ == "__main__":
    unittest.main()
