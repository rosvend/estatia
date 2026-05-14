"""Public surface of the shared graph state.

Re-exports the top-level `PropertyFinderState` plus every nested Pydantic
model so callers can do `from src.state import PropertyFinderState, Listing,
Constraint, EvaluationResult, ...` regardless of the internal file split.
"""

from src.state.evaluation import CandidateScore, EvaluationResult, FailureReason
from src.state.listings import Candidate, Listing, VerifiedListing
from src.state.news import NewsCategory, NewsItem, NewsResults
from src.state.requirements import (
    Constraint,
    ConstraintType,
    Importance,
    StructuredRequirements,
)
from src.state.softening import SofteningAttempt
from src.state.state import PropertyFinderState

__all__ = [
    "Candidate",
    "CandidateScore",
    "Constraint",
    "ConstraintType",
    "EvaluationResult",
    "FailureReason",
    "Importance",
    "Listing",
    "NewsCategory",
    "NewsItem",
    "NewsResults",
    "PropertyFinderState",
    "SofteningAttempt",
    "StructuredRequirements",
    "VerifiedListing",
]
