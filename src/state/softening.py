"""Softener loop memory: one record per relaxation attempt.

The softener reads the full `softening_history` before each new decision so it
doesn't repeat unproductive moves (e.g. relaxing `price` twice when
`bedrooms` is the real blocker). Capped at `max_softening_attempts` by the
graph (currently 3).
"""

from pydantic import BaseModel, Field


class SofteningAttempt(BaseModel):
    """A single relaxation step plus the evaluator's verdict that followed.

    Written by: `softener_agent` *after* the subsequent evaluator pass — i.e.
    each attempt record is "what I did and what happened next", never a
    forward-looking intent.
    Read by: `softener_agent` itself, on its next pass, as episodic memory.
    """

    attempt_number: int = Field(
        ..., description="1-indexed; mirrors `softening_attempts` after the increment for this step."
    )
    relaxed_constraint: str = Field(
        ..., description="The `Constraint.field` that was relaxed in this attempt."
    )
    relaxation_description: str = Field(
        ...,
        description="Human summary of the move, e.g. 'price max raised from 1.0M to 1.15M COP'.",
    )
    previous_value: str = Field(
        ..., description="Rendered constraint value before relaxation, for audit."
    )
    new_value: str = Field(..., description="Rendered constraint value after relaxation.")
    subsequent_candidate_count: int = Field(
        ..., description="How many candidates the next synthesis produced under the relaxed brief."
    )
    subsequent_evaluation_passed: bool = Field(
        ..., description="Whether the evaluator passed after this relaxation."
    )
    evaluator_feedback: str = Field(
        ...,
        description="Concise reason the evaluator gave for accepting or rejecting; guides the next move.",
    )
