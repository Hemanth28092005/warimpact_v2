"""Canonical URL normalization, content hashing, and persistent news_stories deduplication."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from psycopg import AsyncConnection

TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "dclid", "zanpid",
    "ref", "ref_src", "ref_url", "amp", "sessionid",
    "mc_cid", "mc_eid", "_hsenc", "_hsmi", "ncid", "ocid",
}


def normalize_url(raw_url: str) -> str:
    """Normalize URL to canonical representation.

    Rules:
    - Lowercase scheme and domain (netloc)
    - Remove tracking / marketing query parameters
    - Alphabetically sort remaining query parameters
    - Strip fragment identifier (#...)
    - Normalize path slashes (strip trailing slash if length > 1)
    """
    if not raw_url or not raw_url.startswith("http"):
        return raw_url.strip() if raw_url else ""

    try:
        parsed = urlparse(raw_url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Remove default ports
        if netloc.endswith(":80") and scheme == "http":
            netloc = netloc[:-3]
        elif netloc.endswith(":443") and scheme == "https":
            netloc = netloc[:-4]

        # Strip tracking query parameters
        query_items = parse_qsl(parsed.query, keep_blank_values=False)
        filtered_query = [(k, v) for k, v in query_items if k.lower() not in TRACKING_QUERY_PARAMS]
        filtered_query.sort(key=lambda x: (x[0], x[1]))
        new_query = urlencode(filtered_query)

        # Normalize path
        path = parsed.path
        if path.endswith("/") and len(path) > 1:
            path = path.rstrip("/")

        # Strip fragment
        canonical = urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
        return canonical
    except Exception:
        return raw_url.strip()


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hex digest of normalized text."""
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def get_or_create_news_story(
    conn: AsyncConnection,
    raw_url: str,
    title: str,
    source_domain: str | None = None,
) -> tuple[int, str]:
    """Upsert story into persistent news_stories table and return (story_id, canonical_url)."""
    canonical_url = normalize_url(raw_url)
    if not source_domain:
        parsed = urlparse(canonical_url)
        source_domain = parsed.netloc or "unknown"

    content_hash = compute_content_hash(f"{title} {canonical_url}")
    normalized_title = title.strip() if title else ""

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO news_stories (
                canonical_url, content_hash, normalized_title, source_domain,
                first_seen_at, last_seen_at
            ) VALUES (%s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (canonical_url) DO UPDATE SET
                normalized_title = CASE 
                    WHEN LENGTH(EXCLUDED.normalized_title) > LENGTH(news_stories.normalized_title) 
                    THEN EXCLUDED.normalized_title 
                    ELSE news_stories.normalized_title 
                END,
                last_seen_at = NOW()
            RETURNING id, canonical_url;
            """,
            (canonical_url, content_hash, normalized_title, source_domain),
        )
        row = await cur.fetchone()
        return row[0], row[1]
