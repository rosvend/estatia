from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI

from estatia.config import Settings
from estatia.models import EvalResult, Listing, NewsInsight, SellerReport, UserRequest
from estatia.sample_data import SAMPLE_LISTINGS, SAMPLE_NEWS


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
        return response.output_parsed

    def chill_request(self, request: UserRequest, feedback: str) -> UserRequest:
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
        return response.output_parsed

    def evaluate(
        self,
        request: UserRequest,
        listings: list[Listing],
        news: list[NewsInsight],
        threshold: float,
    ) -> EvalResult:
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
        return result.model_copy(update={"threshold": threshold, "passed": result.score >= threshold})

    def build_report(
        self,
        request: UserRequest,
        listings: list[Listing],
        news: list[NewsInsight],
        evaluation: EvalResult,
    ) -> SellerReport:
        response = self.client.responses.parse(
            model=self.settings.quality_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Prepare a concise sales report for shortlisted properties. "
                        "Be specific, practical, and grounded in the provided data."
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
        return response.output_parsed


class SeedListingService(ListingService):
    def search(self, request: UserRequest) -> list[Listing]:
        matches: list[Listing] = []
        nearest_price: float | None = None
        for listing in SAMPLE_LISTINGS:
            if request.location.city and listing.location.city.lower() != request.location.city.lower():
                continue
            if (
                request.location.neighborhood
                and listing.location.neighborhood
                and listing.location.neighborhood.lower() != request.location.neighborhood.lower()
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
                score += 0.4
            if request.budget.max:
                score += max(0.0, 0.4 - abs(listing.price - request.budget.max) / request.budget.max)
            if request.property.bedrooms and listing.property.bedrooms == request.property.bedrooms:
                score += 0.2
            matches.append(listing.model_copy(update={"score": round(score, 3)}))
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:5]


class SeedNewsService(NewsService):
    def search(self, request: UserRequest, listings: list[Listing]) -> list[NewsInsight]:
        if request.location.neighborhood:
            return [item for item in SAMPLE_NEWS if item.neighborhood.lower() == request.location.neighborhood.lower()]
        neighborhoods = {
            listing.location.neighborhood.lower()
            for listing in listings
            if listing.location.neighborhood
        }
        return [item for item in SAMPLE_NEWS if item.neighborhood.lower() in neighborhoods]


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
