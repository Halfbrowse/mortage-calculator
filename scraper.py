"""Immoweb property scraper.

Fetches Belgian real estate listings from Immoweb's search pages using
CloakBrowser (stealth Chromium) and Chrome DevTools Protocol (CDP) network
interception to capture the embedded JSON API responses.
"""

import logging
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from database import upsert_property

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.immoweb.be"
_SEARCH_URL = "https://www.immoweb.be/en/search-results/apartment/for-sale"
_WARMUP_URL = "https://www.immoweb.be/en"


# ─── Public API ───────────────────────────────────────────────────────────────


def scrape_and_store(
    pages: int = 5, min_price: int | None = None, max_price: int | None = None
) -> int:
    """Scrape up to *pages* search-result pages and upsert into the DB.

    Uses CloakBrowser (patched Chromium) with CDP response interception so the
    browser navigates pages naturally, bypassing DataDome fingerprint checks.
    JSON search results are captured from the network layer as the page renders.

    Returns the total number of properties stored.
    """
    from cloakbrowser import launch

    stored = 0

    browser = launch(
        headless=True,
        locale="en-BE",
        humanize=True,
    )

    try:
        page = browser.new_page()

        # Warmup: let the browser establish a real session + cookies
        logger.info("Warming up session via CloakBrowser…")
        page.goto(_WARMUP_URL, wait_until="networkidle", timeout=30_000)
        logger.info("Warmup complete.")

        for page_num in range(1, pages + 1):
            intercepted: list[dict] = []

            def _handle_response(response, _buf=intercepted):
                """CDP response handler — captures JSON from the search API."""
                try:
                    content_type = response.headers.get("content-type", "")
                    if "json" not in content_type:
                        return
                    url = response.url
                    # Match either the HTML search page XHR or a dedicated API path
                    if "search" not in url and "classified" not in url:
                        return
                    data = response.json()
                    raw = data if isinstance(data, list) else data.get("results", [])
                    if not isinstance(raw, list):
                        return
                    props = [_normalise_json(item) for item in raw]
                    props = [p for p in props if p]
                    if props:
                        _buf.extend(props)
                        logger.debug(
                            "CDP intercepted %d properties from %s", len(props), url
                        )
                except Exception:
                    pass

            page.on("response", _handle_response)

            params: dict = {"countries": "BE", "page": page_num, "orderBy": "newest"}
            if min_price:
                params["priceMin"] = min_price
            if max_price:
                params["priceMax"] = max_price

            url = f"{_SEARCH_URL}?{urlencode(params)}"
            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception as exc:
                logger.error("Error navigating to page %d: %s", page_num, exc)
                break

            # Remove handler so it doesn't accumulate across iterations
            page.remove_listener("response", _handle_response)

            props = intercepted

            # Fallback: parse the rendered HTML if CDP captured nothing
            if not props:
                logger.info(
                    "No JSON intercepted on page %d — falling back to HTML parse.",
                    page_num,
                )
                props = _parse_html_page(page.content())

            if not props:
                logger.info("No results on page %d, stopping early.", page_num)
                break

            for prop in props:
                upsert_property(prop)
                stored += 1

            logger.info(
                "Page %d → %d properties (total stored: %d)",
                page_num,
                len(props),
                stored,
            )

            if page_num < pages:
                time.sleep(1.5)

    finally:
        browser.close()

    return stored


# ─── HTML fallback ────────────────────────────────────────────────────────────


def _parse_html_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    props = _extract_from_scripts(soup)
    if props:
        return props
    return _extract_from_cards(soup)


# ── Strategy 1: JSON in <script> tags ─────────────────────────────────────────

_JSON_PATTERNS = [
    r"window\.classified\s*=\s*(\[.+?\])\s*;",
    r'"results"\s*:\s*(\[\s*\{.+?\}\s*\])',
    r"__NUXT__[^=]*=\s*(\{.+\})",
]


def _extract_from_scripts(soup: BeautifulSoup) -> list[dict]:
    import json

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
            if isinstance(raw, list):
                props = [_normalise_json(item) for item in raw]
                props = [p for p in props if p]
                if props:
                    return props
            elif isinstance(raw, dict):
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


# ── Normalise raw JSON classified ─────────────────────────────────────────────


def _normalise_json(item: dict) -> dict | None:
    try:
        prop = item.get("property", item)
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
    articles = []
    for sel in ["article.card--result", "article[data-classified-id]", "article.card"]:
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

        price_el = article.select_one(
            ".card__price, [class*='price'], [data-testid='price']"
        )
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = int(re.sub(r"[^\d]", "", price_text) or 0)
        if price <= 0:
            return None

        title_el = article.select_one("h2, h3, .card__title, [class*='title']")
        title = title_el.get_text(strip=True) if title_el else ""

        loc_el = article.select_one(
            "[class*='locality'], [class*='location'], [data-testid='locality']"
        )
        location = loc_el.get_text(strip=True) if loc_el else ""

        bed_el = article.select_one(
            "[class*='bedroom'], [title*='bedroom'], [aria-label*='bedroom']"
        )
        bedrooms = 0
        if bed_el:
            m = re.search(r"\d+", bed_el.get_text())
            bedrooms = int(m.group()) if m else 0

        area_el = article.select_one(
            "[class*='surface'], [title*='m²'], [aria-label*='m²']"
        )
        area = 0
        if area_el:
            m = re.search(r"\d+", area_el.get_text())
            area = int(m.group()) if m else 0

        link_el = article.select_one("a[href*='classified'], a[href*='immoweb']")
        url = link_el["href"] if link_el else ""
        if url and not url.startswith("http"):
            url = "https://www.immoweb.be" + url

        img_el = article.select_one("img[src], img[data-src]")
        image_url = ""
        if img_el:
            image_url = img_el.get("data-src") or img_el.get("src") or ""

        if not prop_id:
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
