"""Immoweb property scraper.

Fetches Belgian real estate listings from Immoweb's search pages, extracts
property data from the embedded JSON blob, and persists them via database.py.
"""

import json
import logging
import re
import time
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from database import upsert_property

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.immoweb.be"
# JSON API — returns application/json directly (no HTML parsing needed)
_SEARCH_URL = "https://www.immoweb.be/en/search-results/apartment/for-sale"
_WARMUP_URL = "https://www.immoweb.be/en"


_HEADERS_JSON = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Ch-Ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}


# ─── Public API ──────────────────────────────────────────────────────────────


def scrape_and_store(
    pages: int = 5, min_price: int | None = None, max_price: int | None = None
) -> int:
    """Scrape up to *pages* search-result pages and upsert into the DB.

    Returns the total number of properties stored.
    """
    session = requests.Session()
    session.headers.update(_HEADERS_JSON)

    _warmup_with_playwright(session)

    stored = 0
    for page in range(1, pages + 1):
        try:
            props = _fetch_page(session, page, min_price, max_price)
            for prop in props:
                upsert_property(prop)
                stored += 1
            logger.info(
                "Page %d → %d properties (total stored: %d)", page, len(props), stored
            )
            if not props:
                logger.info("No results on page %d, stopping early.", page)
                break
            if page < pages:
                time.sleep(1.5)
        except requests.HTTPError as exc:
            logger.warning(
                "HTTP %s on page %d — stopping.", exc.response.status_code, page
            )
            break
        except Exception as exc:
            logger.error("Error scraping page %d: %s", page, exc)
            break

    return stored


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _warmup_with_playwright(session: requests.Session) -> None:
    """Use a headless Chromium browser to visit the homepage.

    Playwright executes JavaScript, which lets DataDome run its fingerprinting
    challenge and set its cookie.  All resulting cookies are then transferred
    to the requests Session so subsequent API calls are authenticated.
    """
    from urllib.parse import unquote

    from playwright.sync_api import sync_playwright

    logger.info("Warming up session via Playwright (headless Chrome)…")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=_HEADERS_JSON["User-Agent"],
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.goto(_WARMUP_URL, wait_until="networkidle", timeout=30_000)

        # Transfer every cookie Playwright collected into the requests session
        for cookie in context.cookies():
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ".immoweb.be"),
                path=cookie.get("path", "/"),
            )

        browser.close()

    cookie_names = list(session.cookies.keys())
    logger.info("Playwright warmup complete. Cookies: %s", cookie_names)

    xsrf = session.cookies.get("XSRF-TOKEN", "")
    if xsrf:
        session.headers["X-Xsrf-Token"] = unquote(xsrf)
        logger.info("XSRF token acquired.")
    else:
        logger.warning("No XSRF-TOKEN after warmup — API may still reject requests.")


def _fetch_page(
    session: requests.Session,
    page: int,
    min_price: int | None,
    max_price: int | None,
) -> list[dict]:
    params: dict = {"countries": "BE", "page": page, "orderBy": "newest"}
    if min_price:
        params["priceMin"] = min_price
    if max_price:
        params["priceMax"] = max_price

    # Set the Referer so it looks like we navigated from inside the site
    session.headers["Referer"] = _BASE_URL + "/en"

    resp = session.get(_SEARCH_URL, params=params, timeout=20)

    if resp.status_code == 403:
        logger.error(
            "403 Forbidden — DataDome rejected the request despite Playwright warmup. "
            "The datadome cookie may have expired mid-scrape or the session was flagged."
        )
    resp.raise_for_status()

    # The search-results endpoint returns JSON directly
    try:
        data = resp.json()
    except Exception:
        # Fallback: if we got HTML (e.g. a bot-check page), try HTML parsing
        logger.warning("Response was not JSON — falling back to HTML parsing.")
        return _parse_html_page(resp.text)

    # Response shape: {"results": [...], "totalCount": N, ...}
    raw_results = data if isinstance(data, list) else data.get("results", [])
    props = [_normalise_json(item) for item in raw_results]
    return [p for p in props if p]


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
