"""Wire contracts for route matching.

Field names follow the Tier 1/2 vocabulary from CLAUDE.md
(`canonical_origin`, `measured_length_m`, `via_*`, `canonical`) so a value
means the same thing on the wire as it does in the cleaned data.
"""

from pydantic import BaseModel, Field


class JourneyQuery(BaseModel):
    origin: str = Field(..., min_length=1, examples=["GUGULETHU"])
    destination: str = Field(..., min_length=1, examples=["CAPE TOWN"])
    max_changes: int = Field(1, ge=0, le=3,
                             description="Rank changes the rider will accept.")


class RouteSummary(BaseModel):
    objectid: int
    canonical_origin: str
    canonical_destination: str
    # Split per endpoint, matching the cleaned data: "via" metadata is bundled
    # into whichever place name carried it, and the two can differ on one route.
    via_origin: str | None = Field(None, description="Route metadata split out "
                                                     "of the raw origin name.")
    via_destination: str | None = Field(None, description="Route metadata split "
                                                          "out of the raw "
                                                          "destination name.")
    measured_length_m: float = Field(..., description="Haversine over the "
                                                      "coordinates, not a source field.")
    canonical: bool = Field(..., description="Step 6's representative route for "
                                             "this origin/destination pair.")
    issues: list[str] = Field(default_factory=list,
                              description="Step 4/5 flags carried through so a "
                                          "caller can see what is uncertain.")


class JourneyLeg(BaseModel):
    sequence: int
    route: RouteSummary
    board_at: str
    alight_at: str


class JourneyOption(BaseModel):
    legs: list[JourneyLeg]
    total_length_m: float
    changes: int


class JourneyResponse(BaseModel):
    query: JourneyQuery
    options: list[JourneyOption]
    unresolved: list[str] = Field(default_factory=list,
                                  description="Query terms that matched no "
                                              "canonical place.")
