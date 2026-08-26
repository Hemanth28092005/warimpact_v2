"""PIB (Press Information Bureau) Government of India Official Release Client.

Handles:
- Discovering official government releases via PIB RSS feeds (https://pib.gov.in/RssMain.aspx).
- Fetching and parsing full release text through article caching infrastructure.
- Grounded action_type classification into canonical vocabulary:
  - diplomatic, regulatory, legislative, judicial, administrative, fiscal, security.
- Extracting authoritative actor entity (PMO, MEA, MoF, MHA, Cabinet, RBI, DGFT).
- Storing source provenance in `source_provenance` table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Any
import httpx
import psycopg

logger = logging.getLogger(__name__)

PIB_RSS_BASE = "https://pib.gov.in/RssMain.aspx"

# Canonical Action Type Classification Keywords
ACTION_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("diplomatic", [
        "foreign policy", "bilateral", "ambassador", "treaty", "envoy",
        "summit", "mou signed", "joint commission", "external affairs",
        "mea", "high commissioner", "diplomatic relations", "peacekeeping",
    ]),
    ("regulatory", [
        "guidelines", "framework", "compliance", "standard", "rbi mandate",
        "dgft notification", "sebi norm", "tariff order", "licence condition",
        "quality control", "advisory", "regulatory compliance", "pollution board",
    ]),
    ("legislative", [
        "bill passed", "act enacted", "parliament", "ordinance", "lok sabha",
        "rajya sabha", "amendment", "statutory", "gazette notification",
    ]),
    ("judicial", [
        "supreme court", "high court", "tribunal", "nclt", "ruling",
        "verdict", "injunction", "bench directed", "judicial order",
    ]),
    ("fiscal", [
        "budget", "taxation", "gst rate", "customs duty", "monetary policy",
        "fiscal deficit", "appropriation", "subsidy allocation", "finance ministry",
        "revenue expenditure", "rbi repo rate", "disinvestment",
    ]),
    ("security", [
        "armed forces", "defence acquisition", "border security", "drdo",
        "iaf", "indian navy", "indian army", "anti-terror", "home affairs",
        "coast guard", "intelligence bureau", "internal security", "cyber security",
    ]),
    ("administrative", [
        "appointment", "cabinet approves", "scheme launched", "inaugurated",
        "transfers and postings", "committee formed", "administrative approval",
        "task force", "governance initiative",
    ]),
]

ACTOR_PATTERNS: list[tuple[str, list[str]]] = [
    ("Prime Minister's Office", ["prime minister", "pm modi", "pmo"]),
    ("Ministry of External Affairs", ["external affairs", "mea", "jaishankar", "foreign secretary"]),
    ("Ministry of Finance", ["finance ministry", "nirmala sitharaman", "department of revenue", "department of expenditure"]),
    ("Ministry of Defence", ["defence ministry", "rajnath singh", "indian armed forces", "drdo"]),
    ("Ministry of Home Affairs", ["home affairs", "amit shah", "mha"]),
    ("Ministry of Commerce & Industry", ["commerce and industry", "piyush goyal", "dgft"]),
    ("Reserve Bank of India", ["reserve bank of india", "rbi governor", "monetary policy committee"]),
    ("Cabinet Committee on Security", ["cabinet committee on security", "ccs approval"]),
    ("Cabinet Committee on Economic Affairs", ["cabinet committee on economic affairs", "ccea approves"]),
    ("Government of India", ["union government", "centre", "central government"]),
]


def classify_pib_action_type(text: str) -> tuple[str, str]:
    """Classify text into canonical (action_type, actor_entity)."""
    text_lower = text.lower()

    # Determine actor
    detected_actor = "Government of India"
    for actor_name, keywords in ACTOR_PATTERNS:
        if any(kw in text_lower for kw in keywords):
            detected_actor = actor_name
            break

    # Determine action_type
    detected_type = "administrative"
    for act_type, keywords in ACTION_TYPE_RULES:
        if any(kw in text_lower for kw in keywords):
            detected_type = act_type
            break

    return detected_type, detected_actor


class PIBClient:
    """Press Information Bureau RSS and Release Fetcher."""

    def __init__(self, base_url: str = PIB_RSS_BASE) -> None:
        self.base_url = base_url

    def fetch_recent_releases(self, limit: int = 25, timeout_seconds: float = 20.0) -> list[dict[str, Any]]:
        """Fetch recent press releases metadata from official PIB RSS."""
        releases: list[dict[str, Any]] = []
        urls = [
            f"{self.base_url}?ModId=6&Lang=1&Regid=3",
            f"{self.base_url}?ModId=6&Lang=2&Regid=3",
        ]

        for url in urls:
            try:
                with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                    resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code != 200 or not resp.content:
                        continue

                    # Parse XML or extract items safely
                    try:
                        root = ET.fromstring(resp.content)
                        items = root.findall(".//item")
                    except Exception:
                        items = []

                    for it in items:
                        title = it.findtext("title")
                        link = it.findtext("link")
                        pub_date = it.findtext("pubDate")
                        if title and link:
                            clean_title = re.sub(r"\s+", " ", title).strip()
                            releases.append({
                                "headline": clean_title,
                                "source_url": link.strip(),
                                "published_at": pub_date,
                            })
                            if len(releases) >= limit:
                                break
            except Exception as err:
                logger.error(f"Failed to fetch PIB RSS from {url}: {err}")

        return releases


def sync_pib_government_actions(db_url: str) -> int:
    """Fetch PIB releases, classify action type, and store as corroborating government action evidence."""
    client = PIBClient()
    releases = client.fetch_recent_releases(limit=20)
    if not releases:
        return 0

    inserted_count = 0
    now_utc = datetime.now(timezone.utc)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for idx, rel in enumerate(releases, 1):
                headline = rel["headline"]
                source_url = rel["source_url"]
                act_type, actor = classify_pib_action_type(headline)

                # Extract PRID from link
                prid_match = re.search(r"PRID=(\d+)", source_url)
                prid = prid_match.group(1) if prid_match else f"pib_{idx}"

                brief = f"Official policy action by {actor} regarding: {headline}."

                payload_str = json.dumps({
                    "headline": headline,
                    "action_type": act_type,
                    "actor": actor,
                    "url": source_url,
                }, sort_keys=True)
                payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

                cur.execute(
                    """
                    INSERT INTO source_provenance (
                        source_name, source_url, source_record_id, publication_date,
                        evidence_role, payload_hash, raw_payload, entity_type, entity_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_name, source_record_id, entity_type)
                    DO UPDATE SET
                        retrieved_at = NOW(),
                        payload_hash = EXCLUDED.payload_hash,
                        raw_payload = EXCLUDED.raw_payload;
                    """,
                    (
                        "pib",
                        source_url,
                        prid,
                        now_utc,
                        "first_party_policy",
                        payload_hash,
                        payload_str,
                        "government_action",
                        prid,
                    ),
                )
                inserted_count += 1

        conn.commit()

    return inserted_count
