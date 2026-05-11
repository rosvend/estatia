from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urlparse

from estatia.config import Settings
from estatia.models import Listing, ListingLocation, ListingProperty, PropertyType, UserRequest

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - import depends on local environment
    BeautifulSoup = None

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, sync_playwright
except Exception:  # pragma: no cover - import depends on local environment
    PlaywrightError = Exception
    Page = Any
    sync_playwright = None

logger = logging.getLogger("estatia.listing_sources")


SEARCH_DOMAINS = (
    "fincaraiz.com.co",
    "metrocuadrado.com",
    "mercadolibre.com.co",
    "ciencuadras.com",
)


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str


class PlaywrightListingClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, request: UserRequest) -> list[Listing]:
        if sync_playwright is None:
            logger.warning("Playwright is not available in the current environment")
            return []
        if BeautifulSoup is None:
            logger.warning("beautifulsoup4 is not available in the current environment")
            return []
        logger.info(
            "Playwright search:start city=%s neighborhood=%s budget_max=%s radius_km=%s",
            request.location.city,
            request.location.neighborhood,
            request.budget.max,
            request.location.radius_km,
        )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.settings.browser_headless)
                context = browser.new_context()
                context.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in {"image", "font", "media"}
                    else route.continue_(),
                )
                page = context.new_page()
                page.set_default_timeout(self.settings.scrape_timeout_ms)
                results = self._search_results(page, request)
                logger.info("Playwright search:search_results=%s", len(results))
                listings: list[Listing] = []
                for result in results:
                    logger.info("Playwright search:visiting %s", result.url)
                    details_page = context.new_page()
                    details_page.set_default_timeout(self.settings.scrape_timeout_ms)
                    try:
                        details_page.goto(result.url, wait_until="domcontentloaded")
                        listing = self._extract_listing(details_page, result, request)
                        if listing:
                            logger.info("Playwright search:listing_extracted title=%s price=%s", listing.title, listing.price)
                            listings.append(listing)
                        else:
                            logger.warning("Playwright search:listing extraction failed for %s", result.url)
                    except PlaywrightError:
                        logger.exception("Playwright search:page visit failed for %s", result.url)
                        continue
                    finally:
                        details_page.close()
                browser.close()
        except PlaywrightError:
            logger.exception("Playwright search failed")
            return []
        listings.sort(key=lambda item: item.score, reverse=True)
        logger.info("Playwright search:done listings=%s", len(listings[: self.settings.search_results_limit]))
        return listings[: self.settings.search_results_limit]

    def _search_results(self, page: Page, request: UserRequest) -> list[SearchResult]:
        query = self._build_query(request)
        logger.info("Playwright search query=%s", query)
        page.goto(f"https://duckduckgo.com/html/?q={quote_plus(query)}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        anchors = page.locator("a.result__a")
        count = min(anchors.count(), self.settings.search_results_limit * 3)
        results: list[SearchResult] = []
        seen: set[str] = set()
        for index in range(count):
            href = anchors.nth(index).get_attribute("href") or ""
            title = (anchors.nth(index).text_content() or "").strip()
            normalized = self._normalize_url(href)
            if not normalized or normalized in seen:
                continue
            if not any(domain in normalized for domain in SEARCH_DOMAINS):
                continue
            seen.add(normalized)
            results.append(SearchResult(title=title or normalized, url=normalized))
        logger.info("Playwright normalized search results=%s", len(results))
        return results

    def _build_query(self, request: UserRequest) -> str:
        terms = [
            self._intent_term(request),
            self._property_type_term(request.property.type),
            request.location.neighborhood or "",
            " ".join(request.location.alternate_areas),
            request.location.city or "",
        ]
        if request.location.radius_km:
            terms.append(f"{request.location.radius_km} km")
        if request.budget.max:
            terms.append(str(int(request.budget.max)))
        domains = " OR ".join(f"site:{domain}" for domain in SEARCH_DOMAINS)
        return " ".join(term for term in terms if term).strip() + f" ({domains})"

    def _extract_listing(self, page: Page, result: SearchResult, request: UserRequest) -> Listing | None:
        html = page.content()
        metadata = self._extract_structured_candidates(html)
        best = self._pick_candidate(metadata)

        title = self._coalesce(
            best.get("name"),
            best.get("title"),
            page.title(),
            result.title,
        )
        price = self._extract_price(best) or self._extract_price_from_text(page.locator("body").text_content() or "")
        if price is None:
            return None

        address = best.get("address")
        location = ListingLocation(
            city=self._coalesce(self._address_field(address, "addressLocality"), request.location.city, "Unknown"),
            neighborhood=self._coalesce(
                self._address_field(address, "addressRegion"),
                request.location.neighborhood,
            ),
            address=self._format_address(address),
        )

        property_type = self._normalize_property_type(
            self._coalesce(best.get("@type"), best.get("category"), request.property.type.value)
        )
        listing = Listing(
            id=hashlib.md5(result.url.encode("utf-8")).hexdigest()[:12],
            source=urlparse(result.url).netloc,
            url=result.url,
            title=title,
            price=price,
            currency=self._extract_currency(best) or request.budget.currency,
            location=location,
            property=ListingProperty(
                type=property_type,
                bedrooms=self._extract_int(best, ("numberOfRooms", "numberOfBedrooms", "bedrooms")),
                bathrooms=self._extract_int(best, ("numberOfBathroomsTotal", "bathrooms")),
                area_m2=self._extract_area(best),
            ),
            highlights=self._extract_highlights(best),
            images=self._extract_images(best),
            score=self._score_listing(price, location, request),
        )
        return listing

    def _extract_structured_candidates(self, html: str) -> list[dict[str, Any]]:
        if BeautifulSoup is None:
            return []
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[dict[str, Any]] = []
        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text(strip=True)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            candidates.extend(self._flatten_json_ld(data))
        og_title = soup.find("meta", attrs={"property": "og:title"})
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_title:
            candidates.append(
                {
                    "name": og_title.get("content"),
                    "image": og_image.get("content") if og_image else None,
                }
            )
        return candidates

    def _flatten_json_ld(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            items: list[dict[str, Any]] = []
            for entry in data:
                items.extend(self._flatten_json_ld(entry))
            return items
        if not isinstance(data, dict):
            return []
        graph = data.get("@graph")
        if isinstance(graph, list):
            items: list[dict[str, Any]] = []
            for entry in graph:
                items.extend(self._flatten_json_ld(entry))
            return items
        items = [data]
        offers = data.get("offers")
        if isinstance(offers, dict):
            items.append(offers)
        return items

    def _pick_candidate(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        scored = []
        for item in candidates:
            score = 0
            if item.get("price") or item.get("priceSpecification"):
                score += 3
            if item.get("name"):
                score += 2
            if item.get("address"):
                score += 2
            if item.get("@type"):
                score += 1
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1] if scored else {}

    def _extract_price(self, data: dict[str, Any]) -> float | None:
        if "price" in data:
            return self._to_float(data.get("price"))
        price_spec = data.get("priceSpecification")
        if isinstance(price_spec, dict):
            return self._to_float(price_spec.get("price"))
        offers = data.get("offers")
        if isinstance(offers, dict):
            return self._to_float(offers.get("price"))
        return None

    def _extract_price_from_text(self, text: str) -> float | None:
        match = re.search(r"\$?\s?([\d\.\,]{6,})", text)
        if not match:
            return None
        return self._to_float(match.group(1))

    def _extract_currency(self, data: dict[str, Any]) -> str | None:
        for key in ("priceCurrency", "currency"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value.upper()
        offers = data.get("offers")
        if isinstance(offers, dict):
            value = offers.get("priceCurrency")
            if isinstance(value, str) and value:
                return value.upper()
        return None

    def _extract_int(self, data: dict[str, Any], keys: tuple[str, ...]) -> int | None:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                return int(float(str(value)))
            except ValueError:
                continue
        return None

    def _extract_area(self, data: dict[str, Any]) -> int | None:
        area = data.get("floorSize")
        if isinstance(area, dict):
            value = area.get("value")
            numeric = self._to_float(value)
            return int(numeric) if numeric is not None else None
        numeric = self._to_float(data.get("area"))
        return int(numeric) if numeric is not None else None

    def _extract_highlights(self, data: dict[str, Any]) -> list[str]:
        highlights: list[str] = []
        for key in ("description", "category"):
            value = data.get(key)
            if isinstance(value, str) and value:
                highlights.append(value[:180])
        return highlights[:3]

    def _extract_images(self, data: dict[str, Any]) -> list[str]:
        images = data.get("image")
        if isinstance(images, str):
            return [images]
        if isinstance(images, list):
            return [image for image in images if isinstance(image, str)][:3]
        return []

    def _format_address(self, address: Any) -> str | None:
        if not isinstance(address, dict):
            return None
        parts = [
            address.get("streetAddress"),
            address.get("addressLocality"),
            address.get("addressRegion"),
        ]
        clean = [part for part in parts if isinstance(part, str) and part]
        return ", ".join(clean) if clean else None

    def _address_field(self, address: Any, key: str) -> str | None:
        if isinstance(address, dict):
            value = address.get(key)
            if isinstance(value, str):
                return value
        return None

    def _normalize_property_type(self, raw: str) -> PropertyType:
        lowered = raw.lower()
        if "house" in lowered or "casa" in lowered:
            return PropertyType.HOUSE
        if "studio" in lowered:
            return PropertyType.STUDIO
        if "loft" in lowered:
            return PropertyType.LOFT
        if "office" in lowered or "oficina" in lowered:
            return PropertyType.OFFICE
        if "land" in lowered or "lote" in lowered:
            return PropertyType.LAND
        return PropertyType.APARTMENT

    def _score_listing(self, price: float, location: ListingLocation, request: UserRequest) -> float:
        score = 0.2
        if request.location.city and location.city.lower() == request.location.city.lower():
            score += 0.3
        if request.location.neighborhood and location.neighborhood:
            if request.location.neighborhood.lower() in location.neighborhood.lower():
                score += 0.25
        if request.budget.max:
            score += max(0.0, 0.25 - abs(price - request.budget.max) / request.budget.max)
        return round(score, 3)

    def _intent_term(self, request: UserRequest) -> str:
        return {
            "rent": "arriendo apartamento",
            "buy": "venta apartamento",
            "invest": "inversión inmueble",
        }.get(request.intent.value, "inmueble")

    def _property_type_term(self, property_type: PropertyType) -> str:
        return {
            PropertyType.APARTMENT: "apartamento",
            PropertyType.HOUSE: "casa",
            PropertyType.STUDIO: "apartaestudio",
            PropertyType.LOFT: "loft",
            PropertyType.OFFICE: "oficina",
            PropertyType.LAND: "lote",
            PropertyType.ANY: "inmueble",
        }[property_type]

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return ""

    def _coalesce(self, *values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "Listing"

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^\d,\.]", "", str(value))
        if not cleaned:
            return None
        if cleaned.count(",") == 1 and cleaned.count(".") > 1:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif cleaned.count(",") > 1 and cleaned.count(".") == 0:
            cleaned = cleaned.replace(",", "")
        elif "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
