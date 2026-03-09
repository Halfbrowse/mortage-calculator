"""Immoweb property scraper.

Fetches Belgian real estate listings from Immoweb's search pages, extracts
property data from the embedded JSON blob, and persists them via database.py.
"""

import json
import logging
import re
import time
from datetime import UTC, datetime
from urllib.parse import unquote, urlencode

from bs4 import BeautifulSoup

from database import upsert_property

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.immoweb.be"
# JSON API — returns application/json directly (no HTML parsing needed)
_SEARCH_URL = "https://www.immoweb.be/en/search-results/apartment/for-sale"
_WARMUP_URL = "https://www.immoweb.be/en"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

_API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": _BASE_URL + "/en",
}


# ─── Public API ──────────────────────────────────────────────────────────────


def scrape_and_store(
    pages: int = 5, min_price: int | None = None, max_price: int | None = None
) -> int:
    """Scrape up to *pages* search-result pages and upsert into the DB.

    Uses Playwright for all HTTP requests so the TLS fingerprint and session
    cookies stay consistent — DataDome ties cookies to browser fingerprints,
    so switching to a plain requests.Session after warmup triggers a 403.

    Returns the total number of properties stored.
    """
    from playwright.sync_api import sync_playwright

    stored = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=_USER_AGENT,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Warmup: let DataDome fingerprint a real browser navigation
        logger.info("Warming up session via Playwright (headless Chrome)…")
        page.goto(_WARMUP_URL, wait_until="networkidle", timeout=30_000)

        cookie_names = [c["name"] for c in context.cookies()]
        logger.info("Playwright warmup complete. Cookies: %s", cookie_names)

        xsrf = next(
            (
                unquote(c["value"])
                for c in context.cookies()
                if c["name"] == "XSRF-TOKEN"
            ),
            "",
        )
        if xsrf:
            logger.info("XSRF token acquired.")
        else:
            logger.warning(
                "No XSRF-TOKEN after warmup — API may still reject requests."
            )

        extra_headers = {**_API_HEADERS}
        if xsrf:
            extra_headers["X-Xsrf-Token"] = xsrf

        for page_num in range(1, pages + 1):
            params: dict = {"countries": "BE", "page": page_num, "orderBy": "newest"}
            if min_price:
                params["priceMin"] = min_price
            if max_price:
                params["priceMax"] = max_price

            url = f"{_SEARCH_URL}?{urlencode(params)}"
            try:
                resp = context.request.get(url, headers=extra_headers, timeout=20_000)
            except Exception as exc:
                logger.error("Error fetching page %d: %s", page_num, exc)
                break

            if resp.status == 403:
                logger.error(
                    "403 Forbidden on page %d — DataDome rejected even the Playwright "
                    "request context. The session may have been flagged.",
                    page_num,
                )
                break

            if not resp.ok:
                logger.warning("HTTP %d on page %d — stopping.", resp.status, page_num)
                break

            try:
                data = resp.json()
            except Exception:
                logger.warning("Response was not JSON — falling back to HTML parsing.")
                props = _parse_html_page(resp.text())
            else:
                raw_results = (
                    data if isinstance(data, list) else data.get("results", [])
                )
                props = [_normalise_json(item) for item in raw_results]
                props = [p for p in props if p]

            for prop in props:
                upsert_property(prop)
                stored += 1

            logger.info(
                "Page %d → %d properties (total stored: %d)",
                page_num,
                len(props),
                stored,
            )

            if not props:
                logger.info("No results on page %d, stopping early.", page_num)
                break

            if page_num < pages:
                time.sleep(1.5)

        browser.close()

    return stored


def _parse_html_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")

    # Strategy 1: extract JSON blob embedded in a <script> tag
    props = _extract_from_scripts(soup)
    if props:
        return props

    # Strategy 2: parse HTML article cards directly
    return _extract_from_cards(soup)


# ── Strategy 1: JSON in <script> tags ────────────────────────────────────────

# Immoweb embeds search results as JSON in various patterns.
_JSON_PATTERNS = [
    # Modern Immoweb: window.classified = [{...}, ...]
    r"window\.classified\s*=\s*(\[.+?\])\s*;",
    # Result list stored under a "results" key
    r'"results"\s*:\s*(\[\s*\{.+?\}\s*\])',
    # Nuxt/Next __NUXT__ or similar stores
    r"__NUXT__[^=]*=\s*(\{.+\})",
]


def _extract_from_scripts(soup: BeautifulSoup) -> list[dict]:
    for script in soup.find_all("script"):
        text: str = script.string or ""
        if len(text) < 200:
            continue
        for pattern in _JSON_PATTERNS:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            try:
                raw = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            # raw may be a list of classified dicts or a nested object
            if isinstance(raw, list):
                props = [_normalise_json(item) for item in raw]
                props = [p for p in props if p]
                if props:
                    return props
            elif isinstance(raw, dict):
                # Dig one level for a "results" list
                for val in raw.values():
                    if isinstance(val, list) and val:
                        props = [
                            _normalise_json(item)
                            for item in val
                            if isinstance(item, dict)
                        ]
                        props = [p for p in props if p]
                        if props:
                            return props
    return []


def _normalise_json(item: dict) -> dict | None:
    """Convert a raw Immoweb JSON classified object into our schema."""
    try:
        prop = item.get("property", item)  # some responses wrap in "property"
        price_obj = item.get("price", {}) or {}
        price = (
            price_obj.get("mainValue")
            or price_obj.get("mainDisplayValue")
            or price_obj.get("value")
            or prop.get("price")
            or 0
        )
        if isinstance(price, str):
            price = int(re.sub(r"[^\d]", "", price) or 0)
        price = int(price)
        if price <= 0:
            return None

        location = prop.get("location", {}) or {}
        locality = location.get("locality") or location.get("municipality") or ""
        postal = str(location.get("postalCode") or location.get("zip") or "")

        prop_id = str(item.get("id") or item.get("classified_id") or "")
        if not prop_id:
            return None

        prop_type = (
            prop.get("type") or prop.get("subtype") or item.get("mainTypeName") or ""
        ).upper()

        media = item.get("media", {}) or {}
        pictures = media.get("pictures") or []
        image_url = pictures[0].get("largeUrl", "") if pictures else ""

        return {
            "id": prop_id,
            "title": prop.get("title") or f"{prop_type} in {locality}",
            "price": price,
            "location": f"{locality}, {postal}".strip(", "),
            "zip_code": postal,
            "prop_type": prop_type,
            "bedrooms": int(prop.get("bedroomCount") or prop.get("bedroom") or 0),
            "area": int(
                prop.get("netHabitableSurface")
                or prop.get("habitableSurface")
                or prop.get("area")
                or 0
            ),
            "url": f"https://www.immoweb.be/en/classified/{prop_id}",
            "image_url": image_url,
            "scraped_at": datetime.now(UTC).isoformat(),
        }
    except Exception:
        return None


# ── Strategy 2: HTML article cards ────────────────────────────────────────────


def _extract_from_cards(soup: BeautifulSoup) -> list[dict]:
    props = []
    selectors = [
        "article.card--result",
        "article[data-classified-id]",
        "article.card",
    ]
    articles = []
    for sel in selectors:
        articles = soup.select(sel)
        if articles:
            break

    for article in articles:
        prop = _parse_card(article)
        if prop:
            props.append(prop)
    return props


def _parse_card(article) -> dict | None:
    try:
        prop_id = article.get("data-classified-id") or article.get("data-id") or ""

        # Price
        price_el = article.select_one(
            ".card__price, [class*='price'], [data-testid='price']"
        )
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = int(re.sub(r"[^\d]", "", price_text) or 0)
        if price <= 0:
            return None

        # Title
        title_el = article.select_one("h2, h3, .card__title, [class*='title']")
        title = title_el.get_text(strip=True) if title_el else ""

        # Location
        loc_el = article.select_one(
            "[class*='locality'], [class*='location'], [data-testid='locality']"
        )
        location = loc_el.get_text(strip=True) if loc_el else ""

        # Bedrooms
        bed_el = article.select_one(
            "[class*='bedroom'], [title*='bedroom'], [aria-label*='bedroom']"
        )
        bedrooms = 0
        if bed_el:
            m = re.search(r"\d+", bed_el.get_text())
            bedrooms = int(m.group()) if m else 0

        # Area
        area_el = article.select_one(
            "[class*='surface'], [title*='m²'], [aria-label*='m²']"
        )
        area = 0
        if area_el:
            m = re.search(r"\d+", area_el.get_text())
            area = int(m.group()) if m else 0

        # URL
        link_el = article.select_one("a[href*='classified'], a[href*='immoweb']")
        url = link_el["href"] if link_el else ""
        if url and not url.startswith("http"):
            url = "https://www.immoweb.be" + url

        # Image
        img_el = article.select_one("img[src], img[data-src]")
        image_url = ""
        if img_el:
            image_url = img_el.get("data-src") or img_el.get("src") or ""

        if not prop_id:
            # Derive ID from URL
            m = re.search(r"/(\d+)(?:\?|$)", url)
            prop_id = m.group(1) if m else ""

        if not prop_id:
            return None

        return {
            "id": prop_id,
            "title": title,
            "price": price,
            "location": location,
            "zip_code": "",
            "prop_type": "",
            "bedrooms": bedrooms,
            "area": area,
            "url": url,
            "image_url": image_url,
            "scraped_at": datetime.now(UTC).isoformat(),
        }
    except Exception:
        return None
