"""Evaluator output: per-candidate scores plus aggregate failure reasons.

`aggregate_failure_reasons` is the softener's primary input — it tells the
softener which constraints to relax and by how much, without needing to
re-derive that from per-candidate scores.
"""

from pydantic import BaseModel, Field

from src.state.requirements import Importance


class FailureReason(BaseModel):
    """A single constraint violation observed during evaluation.

    Written by: `evaluator_agent`.
    Read by: `softener_agent` (to choose the next relaxation).
    """

    constraint_field: str = Field(
        ..., description="Which `Constraint.field` was violated (e.g. 'price')."
    )
    expected: str = Field(
        ...,
        description="Rendered representation of the requirement, e.g. '<= 1,000,000,000 COP'.",
    )
    actual: str = Field(
        ..., description="Rendered representation of the candidate's value, e.g. '1,150,000,000 COP'."
    )
    deviation: float | None = Field(
        default=None,
        description="Normalized magnitude of the miss (e.g. 0.15 = 15% over). Drives softener step sizing.",
    )
    importance: Importance = Field(
        ..., description="Mirrors the originating Constraint.importance for prioritization."
    )


class CandidateScore(BaseModel):
    """The evaluator's verdict on a single candidate.

    Written by: `evaluator_agent`. Read by: `synthesizer_agent` (for ranking
    in `final_results`), and the softener as supporting context.
    """

    candidate_id: str = Field(
        ..., description="The `Candidate.listing.id` this score corresponds to."
    )
    score: float = Field(..., description="Aggregate score in [0, 1]; 1.0 is a perfect match.")
    violated_constraints: list[FailureReason] = Field(
        default_factory=list,
        description="All constraints this candidate violates; empty means a clean pass.",
    )
    matched_constraint_fields: list[str] = Field(
        default_factory=list,
        description="Constraint field names this candidate satisfies. Names only — full Constraint lives in `requirements`.",
    )


class EvaluationResult(BaseModel):
    """The evaluator's full output for one synthesis-iteration's candidate set.

    Written by: `evaluator_agent`.
    Read by: `evaluation_router` (via `.passes`), `softener_agent`,
    `done_node`, `best_effort_node`.
    """

    passes: bool = Field(
        ...,
        description="True iff at least one candidate satisfies all hard constraints. Read by evaluation_router.",
    )
    candidate_scores: list[CandidateScore] = Field(
        default_factory=list, description="Per-candidate verdicts, in evaluator-determined order."
    )
    aggregate_failure_reasons: list[FailureReason] = Field(
        default_factory=list,
        description="Cross-candidate roll-up of violations; softener's primary input.",
    )
    notes: str | None = Field(
        default=None, description="Free-text evaluator commentary for traceability / debugging."
    )
