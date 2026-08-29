from pydantic import BaseModel, Field


class Place(BaseModel):
    canonical_name: str
    lon: float | None = Field(None, description="Consensus longitude across all "
                                                "routes claiming this place.")
    lat: float | None = None
    endpoint_count: int = Field(..., description="How many route endpoints claim "
                                                 "this place.")
    consensus_verifiable: bool = Field(
        ..., description="False when fewer than min_consensus_support endpoints "
                         "claim it -- the consensus is then just the one endpoint "
                         "and proves nothing.")
    raw_names: list[str] = Field(default_factory=list,
                                 description="Published ORGN/DSTN spellings that "
                                             "normalise to this place.")


class PlaceSearchResult(BaseModel):
    query: str
    matches: list[Place]


class NameExplanation(BaseModel):
    """Mirrors `python -m pipeline explain <NAME>` over HTTP."""

    raw: str
    canonical: str
    changed: bool
    via: str | None = None
    trace: list[dict] = Field(
        default_factory=list,
        description="Each transform applied, in order. Structured rather than "
                    "flattened: every stage carries the rule and the evidence "
                    "behind it, which is what makes a merge reviewable.")
    review_codes: list[str] = Field(
        default_factory=list,
        description="Why this resolution may not be trustworthy, e.g. "
                    "low_support_place.")
