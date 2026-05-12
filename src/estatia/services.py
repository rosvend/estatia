from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from openai import OpenAI

from estatia.config import Settings
from estatia.listing_sources import PlaywrightListingClient
from estatia.models import EvalResult, Listing, NewsInsight, SellerReport, UserRequest
from estatia.sample_data import SAMPLE_LISTINGS, SAMPLE_NEWS

logger = logging.getLogger("estatia.services")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii").strip().lower()


class IntakeService(Protocol):
    def parse_request(self, raw_text: str) -> UserRequest: ...

    def chill_request(self, request: UserRequest, feedback: str) -> UserRequest: ...


class EvaluationService(Protocol):
    def evaluate(
        self,
        request: UserRequest,
        listings: list[Listing],
        news: list[NewsInsight],
        threshold: float,
    ) -> EvalResult: ...


class SellerService(Protocol):
    def build_report(
        self,
        request: UserRequest,
        listings: list[Listing],
        news: list[NewsInsight],
        evaluation: EvalResult,
        language: str,
    ) -> SellerReport: ...


class ListingService(Protocol):
    def search(self, request: UserRequest) -> list[Listing]: ...


class NewsService(Protocol):
    def search(self, request: UserRequest, listings: list[Listing]) -> list[NewsInsight]: ...


class WhatsAppService(Protocol):
    def validate(self, listings: list[Listing]) -> list[str]: ...


class OpenAIWorkflowService(IntakeService, EvaluationService, SellerService):
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required to run the workflow.")
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def parse_request(self, raw_text: str) -> UserRequest:
        logger.info("OpenAI parse_request:start")
        response = self.client.responses.parse(
            model=self.settings.fast_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract a real-estate search request into the provided schema. "
                        "Prefer explicit values from the user. Use null when unknown. "
                        "Keep the summary short and factual."
                    ),
                },
                {"role": "user", "content": raw_text},
            ],
            text_format=UserRequest,
        )
        logger.info("OpenAI parse_request:done")
        return response.output_parsed

    def chill_request(self, request: UserRequest, feedback: str) -> UserRequest:
        logger.info("OpenAI chill_request:start")
        response = self.client.responses.parse(
            model=self.settings.fast_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Relax a real-estate search request so it becomes searchable. "
                        "Do not invent new priorities. Preserve the user intent. "
                        "You may relax any blocking constraint: budget, neighborhood scope, property type, "
                        "bedroom/bathroom/area targets, and strict must-have filters. "
                        "If the requested budget is too low for the target area, raise the budget ceiling "
                        "to the nearest viable market range and mark the budget as flexible. "
                        "If the area is too narrow, widen it to nearby neighborhoods. "
                        "If the area is too broad and noisy, narrow it to the most promising zone. "
                        "If constraints are too strict, move secondary preferences into nice_to_have. "
                        "Keep the same city unless the failure feedback clearly says the city itself has no matches."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Original request:\n{request.model_dump_json(indent=2)}\n\n"
                        f"Why it failed:\n{feedback}\n\n"
                        "Important rules:\n"
                        "- Relax the smallest number of constraints needed to make the search viable.\n"
                        "- Budget can be raised.\n"
                        "- Area can be widened or narrowed.\n"
                        "- Room count, area, property type, and must-have filters can be relaxed.\n"
                        "- Do not invent new preferences that were never implied by the user."
                    ),
                },
            ],
            text_format=UserRequest,
        )
        logger.info("OpenAI chill_request:done")
        return response.output_parsed

    def evaluate(
        self,
        request: UserRequest,
        listings: list[Listing],
        news: list[NewsInsight],
        threshold: float,
    ) -> EvalResult:
        logger.info("OpenAI evaluate:start listings=%s news=%s", len(listings), len(news))
        listing_blob = [listing.model_dump(mode="json") for listing in listings]
        news_blob = [item.model_dump(mode="json") for item in news]
        response = self.client.responses.parse(
            model=self.settings.quality_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Evaluate whether the candidate properties fit the request. "
                        "Be strict about budget, location fit, and must-have constraints."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Threshold: {threshold}\n"
                        f"Request:\n{request.model_dump_json(indent=2)}\n\n"
                        f"Listings:\n{listing_blob}\n\n"
                        f"News:\n{news_blob}"
                    ),
                },
            ],
            text_format=EvalResult,
        )
        result = response.output_parsed
        logger.info("OpenAI evaluate:done score=%.2f", result.score)
        return result.model_copy(update={"threshold": threshold, "passed": result.score >= threshold})

    def build_report(
        self,
        request: UserRequest,
        listings: list[Listing],
        news: list[NewsInsight],
        evaluation: EvalResult,
        language: str,
    ) -> SellerReport:
        logger.info("OpenAI build_report:start listings=%s", len(listings))
        language_name = "Spanish" if language == "es" else "English"
        response = self.client.responses.parse(
            model=self.settings.quality_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Prepare a concise sales report for shortlisted properties. "
                        "Be specific, practical, and grounded in the provided data. "
                        f"Write the report in {language_name}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Request:\n{request.model_dump_json(indent=2)}\n\n"
                        f"Listings:\n{[item.model_dump(mode='json') for item in listings]}\n\n"
                        f"News:\n{[item.model_dump(mode='json') for item in news]}\n\n"
                        f"Evaluation:\n{evaluation.model_dump_json(indent=2)}"
                    ),
                },
            ],
            text_format=SellerReport,
        )
        logger.info("OpenAI build_report:done")
        return response.output_parsed.model_copy(update={"language": language})


class SeedListingService(ListingService):
    def search(self, request: UserRequest) -> list[Listing]:
        logger.info("Seed listing search:start city=%s neighborhood=%s budget_max=%s", request.location.city, request.location.neighborhood, request.budget.max)
        matches: list[Listing] = []
        nearest_price: float | None = None
        for listing in SAMPLE_LISTINGS:
            if request.location.city and normalize_text(listing.location.city) != normalize_text(request.location.city):
                continue
            if (
                request.location.neighborhood
                and listing.location.neighborhood
                and normalize_text(listing.location.neighborhood) != normalize_text(request.location.neighborhood)
            ):
                continue
            if nearest_price is None or listing.price < nearest_price:
                nearest_price = listing.price
            if request.budget.max and listing.price > request.budget.max:
                continue
            if request.property.type.value != "any" and listing.property.type != request.property.type:
                continue
            if request.property.bedrooms and (listing.property.bedrooms or 0) < request.property.bedrooms:
                continue
            score = 0.0
            if request.location.neighborhood and listing.location.neighborhood:
                if normalize_text(request.location.neighborhood) == normalize_text(listing.location.neighborhood):
                    score += 0.4
            if request.budget.max:
                score += max(0.0, 0.4 - abs(listing.price - request.budget.max) / request.budget.max)
            if request.property.bedrooms and listing.property.bedrooms == request.property.bedrooms:
                score += 0.2
            matches.append(listing.model_copy(update={"score": round(score, 3)}))
        matches.sort(key=lambda item: item.score, reverse=True)
        logger.info("Seed listing search:done matches=%s", len(matches[:5]))
        return matches[:5]


class PlaywrightListingService(ListingService):
    def __init__(self, settings: Settings, fallback: ListingService | None = None) -> None:
        self.client = PlaywrightListingClient(settings)
        self.fallback = fallback

    def search(self, request: UserRequest) -> list[Listing]:
        logger.info("Playwright listing search:start")
        listings = self.client.search(request)
        if listings:
            logger.info("Playwright listing search:done listings=%s", len(listings))
            return listings
        if self.fallback is not None:
            logger.warning("Playwright listing search returned no listings, falling back to seed data")
            return self.fallback.search(request)
        logger.warning("Playwright listing search returned no listings and no fallback is configured")
        return []


CITY_NEIGHBORHOODS: dict[str, list[str]] = {
    "bogota": ["Chico Norte", "Cedritos", "Teusaquillo", "Rosales", "Chapinero", "Usaquen"],
    "medellin": ["Laureles", "El Poblado", "Envigado", "Sabaneta", "Belen", "Los Colores"],
    "cali": ["Ciudad Jardin", "Granada", "San Fernando", "El Ingenio", "Pance"],
}


class TavilyNewsService(NewsService):
    def __init__(self, settings: Settings, fallback: NewsService | None = None) -> None:
        self.settings = settings
        self.api_key = settings.tavily_api_key
        self.fallback = fallback

    def search(self, request: UserRequest, listings: list[Listing]) -> list[NewsInsight]:
        if not self.api_key:
            logger.warning("Tavily news search skipped because TAVILY_API_KEY is not configured")
            return self._fallback(request, listings)

        neighborhoods = self._candidate_neighborhoods(request, listings)
        query = self._build_query(request, neighborhoods)
        payload = {
            "api_key": self.api_key,
            "query": query,
            "topic": "news",
            "search_depth": "basic",
            "time_range": "month",
            "max_results": self.settings.news_results_limit,
            "include_answer": False,
            "include_raw_content": False,
        }
        logger.info(
            "Tavily news search:start city=%s neighborhoods=%s",
            request.location.city,
            neighborhoods,
        )
        try:
            response = self._post_search(payload)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Tavily news search failed: %s", exc)
            return self._fallback(request, listings)

        insights = self._build_insights(response, neighborhoods, request)
        logger.info("Tavily news search:done insights=%s", len(insights))
        if insights:
            return insights
        return self._fallback(request, listings)

    def _post_search(self, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        request = UrlRequest(
            "https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _candidate_neighborhoods(
        self,
        request: UserRequest,
        listings: list[Listing],
    ) -> list[str]:
        if request.location.neighborhood:
            return [request.location.neighborhood]

        candidates: list[str] = []
        for area in request.location.alternate_areas:
            if area and area not in candidates:
                candidates.append(area)

        for listing in listings:
            neighborhood = listing.location.neighborhood
            if neighborhood and neighborhood not in candidates:
                candidates.append(neighborhood)

        city_key = normalize_text(request.location.city)
        for area in CITY_NEIGHBORHOODS.get(city_key, []):
            if area not in candidates:
                candidates.append(area)

        return candidates[:6]

    def _build_query(self, request: UserRequest, neighborhoods: list[str]) -> str:
        city = request.location.city or "the city"
        intent = "rental" if request.intent.value == "rent" else "property"
        focus = ", ".join(neighborhoods[:4]) if neighborhoods else city
        return (
            f"{city} Colombia neighborhood news {focus} "
            f"safety transport development walkability demand {intent}"
        )

    def _build_insights(
        self,
        response: dict[str, object],
        neighborhoods: list[str],
        request: UserRequest,
    ) -> list[NewsInsight]:
        results = response.get("results", [])
        if not isinstance(results, list):
            return []

        insights: list[NewsInsight] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            summary = str(item.get("content") or item.get("snippet") or "").strip()
            source = str(item.get("source") or item.get("domain") or "Tavily").strip()
            if not title or not url or not summary:
                continue
            neighborhood = self._detect_neighborhood(title, summary, neighborhoods, request)
            if not neighborhood:
                continue
            try:
                insights.append(
                    NewsInsight(
                        neighborhood=neighborhood,
                        title=title,
                        summary=summary[:420],
                        source=source,
                        url=url,
                    )
                )
            except Exception:
                continue
        return insights[: self.settings.news_results_limit]

    def _detect_neighborhood(
        self,
        title: str,
        summary: str,
        neighborhoods: list[str],
        request: UserRequest,
    ) -> str | None:
        haystack = normalize_text(f"{title} {summary}")
        for neighborhood in neighborhoods:
            if normalize_text(neighborhood) and normalize_text(neighborhood) in haystack:
                return neighborhood
        if request.location.neighborhood:
            return request.location.neighborhood
        return request.location.city

    def _fallback(self, request: UserRequest, listings: list[Listing]) -> list[NewsInsight]:
        if self.fallback is None:
            return []
        logger.info("Tavily news search:fallback")
        return self.fallback.search(request, listings)


class SeedNewsService(NewsService):
    def search(self, request: UserRequest, listings: list[Listing]) -> list[NewsInsight]:
        if request.location.neighborhood:
            return [
                item
                for item in SAMPLE_NEWS
                if normalize_text(item.neighborhood) == normalize_text(request.location.neighborhood)
            ]
        neighborhoods = {
            normalize_text(listing.location.neighborhood)
            for listing in listings
            if listing.location.neighborhood
        }
        return [item for item in SAMPLE_NEWS if normalize_text(item.neighborhood) in neighborhoods]


class StandbyWhatsAppService(WhatsAppService):
    def validate(self, listings: list[Listing]) -> list[str]:
        return [f"{listing.id}: standby validation disabled" for listing in listings]


@dataclass(slots=True)
class Services:
    intake: IntakeService
    evaluation: EvaluationService
    seller: SellerService
    listing: ListingService
    news: NewsService
    whatsapp: WhatsAppService
