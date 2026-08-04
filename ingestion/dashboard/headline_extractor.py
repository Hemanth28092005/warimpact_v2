"""Title-only headline extractor for GDELT source URLs.

Extracts page HTML <title> or og:title.
Does NOT extract article body text or use trafilatura body caps.
"""

import re
import urllib.request
import logging

logger = logging.getLogger(__name__)

TITLE_REGEX = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
OG_TITLE_REGEX = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
OG_TITLE_REGEX_ALT = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', re.IGNORECASE)


def extract_page_title(source_url: str, timeout_seconds: int = 2) -> str | None:
    """Fetch URL and extract page title tag or og:title.
    
    Returns clean headline string or None if un-fetchable.
    """
    if not source_url or not source_url.startswith("http"):
        return None

    try:
        req = urllib.request.Request(
            source_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            # Read first 32KB which contains <head>
            html_chunk = resp.read(32768).decode("utf-8", errors="ignore")

        # Try og:title first
        og_match = OG_TITLE_REGEX.search(html_chunk) or OG_TITLE_REGEX_ALT.search(html_chunk)
        if og_match:
            title = og_match.group(1).strip()
            if len(title) > 5:
                return _clean_headline(title)

        # Fallback to <title>
        title_match = TITLE_REGEX.search(html_chunk)
        if title_match:
            title = title_match.group(1).strip()
            if len(title) > 5:
                return _clean_headline(title)

    except Exception as e:
        logger.debug(f"Title extraction failed for {source_url}: {e}")

    return None


def _clean_headline(raw_title: str) -> str:
    """Clean HTML entities and trailing site names from title."""
    title = re.sub(r"\s+", " ", raw_title)
    # Remove HTML entities
    title = title.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
    # Strip common site suffixes like " - Reuters", " | BBC News"
    parts = re.split(r"\s+[\|\-\–\—]\s+", title)
    if len(parts) > 1 and len(parts[0]) > 15:
        return parts[0].strip()
    return title.strip()
