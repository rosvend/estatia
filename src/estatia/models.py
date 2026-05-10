from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Intent(str, Enum):
    RENT = "rent"
    BUY = "buy"
    INVEST = "invest"


class PropertyType(str, Enum):
    APARTMENT = "apartment"
    HOUSE = "house"
    STUDIO = "studio"
    LOFT = "loft"
    OFFICE = "office"
    LAND = "land"
    ANY = "any"


class Location(BaseModel):
    city: str | None = None
    country: str | None = None
    neighborhood: str | None = None


class Budget(BaseModel):
    currency: str = "COP"
    min: float | None = None
    max: float | None = None
    payment_type: str | None = None
    is_flexible: bool = False

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PropertyPreferences(BaseModel):
    type: PropertyType = PropertyType.ANY
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_m2: int | None = None


class Constraints(BaseModel):
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    dealbreakers: list[str] = Field(default_factory=list)


class Timeline(BaseModel):
    move_in_by: str | None = None
    urgency: str | None = None


class UserRequest(BaseModel):
    intent: Intent = Intent.RENT
    location: Location = Field(default_factory=Location)
    budget: Budget = Field(default_factory=Budget)
    property: PropertyPreferences = Field(default_factory=PropertyPreferences)
    constraints: Constraints = Field(default_factory=Constraints)
    timeline: Timeline = Field(default_factory=Timeline)
    raw_text: str
    search_summary: str


class ListingLocation(BaseModel):
    city: str
    neighborhood: str | None = None
    address: str | None = None


class ListingProperty(BaseModel):
    type: PropertyType
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_m2: int | None = None


class Listing(BaseModel):
    id: str
    source: str
    url: HttpUrl
    title: str
    price: float
    currency: str = "COP"
    location: ListingLocation
    property: ListingProperty
    highlights: list[str] = Field(default_factory=list)
    images: list[HttpUrl] = Field(default_factory=list)
    posted_at: str | None = None
    availability: str | None = "unknown"
    score: float = 0.0


class NewsInsight(BaseModel):
    neighborhood: str
    title: str
    summary: str
    source: str
    url: HttpUrl


class EvalResult(BaseModel):
    score: float
    threshold: float
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    listing_id: str
    title: str
    neighborhood: str | None = None
    price: float
    currency: str = "COP"
    why_it_fits: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class SellerReport(BaseModel):
    title: str
    summary: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    budget_fit: list[str] = Field(default_factory=list)
    market_notes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    node: str
    message: str

