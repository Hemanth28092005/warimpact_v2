"""Title-only headline extractor for GDELT source URLs.

Extracts page HTML <title>, og:title, twitter:title, or high-confidence URL slug headline.
Applies HTML entity decoding, sanitization, extraction-leakage stripping, and trailing site name removal.
Includes in-memory URL title cache.
"""

from __future__ import annotations

import gzip
import html
import logging
import re
import urllib.parse
import urllib.request
import zlib

logger = logging.getLogger(__name__)

TITLE_REGEX = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
OG_TITLE_REGEX = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:title|twitter:title|title)["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
OG_TITLE_REGEX_ALT = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:title|twitter:title|title)["\']', re.IGNORECASE)
H1_REGEX = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)

_HEADLINE_CACHE: dict[str, str | None] = {}


def extract_page_title(source_url: str, timeout_seconds: int = 1) -> str | None:
    """Fetch URL and extract page title tag or og:title.
    
    Returns clean headline string or None if un-fetchable and no slug available.
    """
    if not source_url or not source_url.startswith("http"):
        return None

    if source_url in _HEADLINE_CACHE:
        return _HEADLINE_CACHE[source_url]

    # Step 1: High-confidence URL slug extraction first (instant, zero-network)
    slug_title = _extract_headline_from_url_slug(source_url)
    if slug_title and len(slug_title) >= 20 and not _is_generic_site_title(slug_title) and len(slug_title.split()) >= 4:
        _HEADLINE_CACHE[source_url] = slug_title
        return slug_title

    result: str | None = None

    # Step 2: Attempt HTTP Fetch if slug was insufficient
    html_content = _fetch_page_head(source_url, timeout_seconds=timeout_seconds)

    if html_content:
        # Try og:title / twitter:title first
        og_match = OG_TITLE_REGEX.search(html_content) or OG_TITLE_REGEX_ALT.search(html_content)
        if og_match:
            title = _clean_headline(og_match.group(1))
            if len(title) >= 12 and not _is_generic_site_title(title):
                result = title

        # Fallback to <title>
        if not result:
            title_match = TITLE_REGEX.search(html_content)
            if title_match:
                title = _clean_headline(title_match.group(1))
                if len(title) >= 12 and not _is_generic_site_title(title):
                    result = title

        # Fallback to <h1>
        if not result:
            h1_match = H1_REGEX.search(html_content)
            if h1_match:
                h1_clean = re.sub(r"<[^>]+>", "", h1_match.group(1))
                title = _clean_headline(h1_clean)
                if len(title) >= 12 and not _is_generic_site_title(title):
                    result = title

    # Step 3: Fallback to partial slug if fetch failed
    if not result and slug_title and len(slug_title) >= 15 and not _is_generic_site_title(slug_title):
        result = slug_title

    _HEADLINE_CACHE[source_url] = result
    return result


def _fetch_page_head(source_url: str, timeout_seconds: int = 3) -> str | None:
    """Fetch first 64KB of page HTML with standard browser headers."""
    try:
        req = urllib.request.Request(
            source_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw_bytes = resp.read(65536)
            encoding = resp.headers.get("Content-Encoding", "").lower()
            if "gzip" in encoding:
                try:
                    raw_bytes = gzip.decompress(raw_bytes)
                except Exception:
                    pass
            elif "deflate" in encoding:
                try:
                    raw_bytes = zlib.decompress(raw_bytes)
                except Exception:
                    pass

            return raw_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.debug(f"HTTP title fetch failed for {source_url}: {e}")
        return None


def _clean_headline(raw_title: str) -> str:
    """Clean HTML entities, fix mojibake, strip extraction leakage, and normalize title."""
    if not raw_title:
        return ""

    # Unescape HTML entities
    title = html.unescape(raw_title)
    title = html.unescape(title)

    # Strip HTML tags if any present
    title = re.sub(r"<[^>]+>", " ", title)

    # Fix common UTF-8 mojibake patterns
    title = title.replace("â€”", "—").replace("â€“", "–")
    title = title.replace("â€˜", "'").replace("â€™", "'")
    title = title.replace("â€œ", '"').replace('â€"', '"')
    title = title.replace("â€¦", "...")

    # Normalize unicode quotes and dashes
    title = title.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    title = title.replace("\u2013", "–").replace("\u2014", " — ").replace("\u00a0", " ")
    title = title.replace("&#34;", '"').replace("&#39;", "'").replace("&quot;", '"')

    # Normalize whitespace
    title = re.sub(r"\s+", " ", title).strip()

    # Strip leading stray date leakage (e.g., '07 22 ', '08/22/2026 ', '2026-08-04 ')
    title = re.sub(r"^(?:\d{1,2}\s+\d{1,2}\s+|\d{4}[-/]\d{2}[-/]\d{2}\s*|\d{2}[-/]\d{2}[-/]\d{4}\s*)", "", title)

    # Strip leading stray dots/punctuation (e.g. '.scottish Labour', '.uk ')
    title = re.sub(r"^[.\-—–:,;\s]+", "", title)

    # Strip common site suffixes like " - Times of India", " | Reuters", " - The Hindu", " - ANI News"
    parts = re.split(r"\s+[\|\-\–\—]\s+", title)
    if len(parts) > 1 and len(parts[0]) >= 15:
        candidate = parts[0].strip()
        if not candidate.lower().startswith("tag:") and not candidate.lower().startswith("category:"):
            return candidate

    return title.strip()


def _extract_headline_from_url_slug(url: str) -> str | None:
    """Extract and reconstruct human-readable headline from news URL path slug."""
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.rstrip("/")
        if not path:
            return None

        segments = [s for s in path.split("/") if s]
        if not segments:
            return None

        candidate_slug = ""
        for seg in reversed(segments):
            clean_seg = re.sub(r"\.(html|htm|cms|ece|php|asp|aspx)$", "", seg, flags=re.I)
            clean_seg = re.sub(r"^\d{4,}-?", "", clean_seg)
            clean_seg = re.sub(r"-?\d{5,}$", "", clean_seg)
            # Remove leading date patterns in slug like '07-22-' or '2026-08-04-'
            clean_seg = re.sub(r"^(?:\d{4}[-_]\d{2}[-_]\d{2}[-_]?|\d{2}[-_]\d{2}[-_]?|\d{2}[-_]\d{2}[-_]\d{4}[-_]?)", "", clean_seg)
            if "-" in clean_seg or "_" in clean_seg:
                words = re.split(r"[-_]+", clean_seg)
                if len(words) >= 4:
                    candidate_slug = " ".join(words).strip()
                    break

        if not candidate_slug or len(candidate_slug) < 15:
            return None

        words = candidate_slug.split()
        capitalized = []
        for i, w in enumerate(words):
            if i == 0 or w.lower() not in {"a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "but", "or", "is", "as"}:
                capitalized.append(w.capitalize())
            else:
                capitalized.append(w.lower())

        result = " ".join(capitalized)
        result = _clean_headline(result)
        return result if len(result) >= 15 else None
    except Exception:
        return None


def _is_generic_site_title(title: str) -> bool:
    """Check if title is a generic non-headline site home/tag title."""
    t_low = title.lower().strip()
    if len(t_low) < 10:
        return True
    generic_starters = [
        "tag:", "category:", "archive for", "latest news", "breaking news",
        "home page", "welcome to", "news update", "index of", "404 not found",
        "page not found", "access denied", "just a moment..."
    ]
    return any(t_low.startswith(g) for g in generic_starters)
